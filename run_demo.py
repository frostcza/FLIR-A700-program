# -*- coding: utf-8 -*-
import sys
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPalette, QColor, QPixmap, QBitmap, QIcon
from PyQt5.QtWidgets import QMainWindow, QApplication, QGraphicsPixmapItem, QGraphicsScene

from demo_ui import Ui_Form
from qt_material import apply_stylesheet

import os
os.environ['KMP_DUPLICATE_LIB_OK']='True'

import PySpin
import subprocess
import threading
import signal
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import time

class MyMainForm(QMainWindow, Ui_Form):
    def __init__(self, parent=None):
        super(MyMainForm, self).__init__(parent)
        self.setupUi(self)
        extra = {'font_family': 'Times New Roman', 'font_size': 32}
        
        bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
        path_css = os.path.abspath(os.path.join(bundle_dir, 'custom.css'))
        path_mask1 = os.path.abspath(os.path.join(bundle_dir, 'mask.png'))
        path_mask2 = os.path.abspath(os.path.join(bundle_dir, 'white_mask.png'))

        apply_stylesheet(app, 'light_blue.xml', invert_secondary=True, extra=extra, css_file=path_css)
        
        path_ico = os.path.abspath(os.path.join(bundle_dir, 'my_demo.ico'))
        self.setWindowIcon(QIcon(path_ico))
        
        self.pixmap_transparent = QPixmap(path_mask1)
        self.pixmap_white = QPixmap(path_mask2)
        
        self.streaming = False
        self.MODE = 'png'
        self.image_save_path = './images/'
        if not os.path.exists(self.image_save_path):
            os.makedirs(self.image_save_path)
        
        self.frame_num = 0
        self.focusing = False
        self.focus_count = 0
        self.FOCUS_STEP = 8
        
        self.frame_delay = -1
        self.frame_delay_const = 1

        self.recording = False
        self.record_list = []
        self.record_index = 1
        self.video_save_path = './video/'
        if not os.path.exists(self.video_save_path):
            os.makedirs(self.video_save_path)

        self.thread_pool = ThreadPoolExecutor(max_workers=5)

        self.radioButton_1.clicked.connect(self.format_png)
        self.radioButton_2.clicked.connect(self.format_raw)
        
        self.pushButton_1.clicked.connect(self.control_start)
        self.pushButton_2.clicked.connect(self.control_stop)
        self.pushButton_3.clicked.connect(self.control_save)
        self.pushButton_4.clicked.connect(self.control_exit)
        self.pushButton_5.clicked.connect(self.focus_further)
        self.pushButton_6.clicked.connect(self.focus_closer)
        self.pushButton_7.clicked.connect(self.nuc_on)
        self.pushButton_8.clicked.connect(self.nuc_off)
        self.pushButton_9.clicked.connect(self.noise_reduce_on)
        self.pushButton_10.clicked.connect(self.noise_reduce_off)
        self.pushButton_11.clicked.connect(self.adjst_on)
        self.pushButton_12.clicked.connect(self.adjust_off)
        self.pushButton_13.clicked.connect(self.control_record)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.acquire_images)
        
    def write_to_textbrowser(self, line):
        self.textBrowser_1.append(line)
        self.textBrowser_1.ensureCursorVisible()
        
    def run_video(self):
        command = "ffplay -x 640 -y 480 -left 980 -top 90 -i -noborder rtsp://192.168.0.1/mjpg/ch1 \
            -fflags nobuffer -analyzeduration 500000 \
            -probesize 500000 -flags low_delay -vf setpts=0"
            
        self.pid1 = subprocess.Popen(command)
    
    def accurate_delay(self, delay):
        _ = time.perf_counter() + delay/1000
        while time.perf_counter() < _:
            pass
    
    def start_vi_save(self, frame_num):
        command = f"ffmpeg -i rtsp://192.168.0.1/mjpg/ch1 -frames:v 1 -y \
            \"./images/my_vistream-{frame_num}.png\"" 
        subprocess.call(command)
        print('VI Image saved at ./images/my_vistream-' + str(frame_num) + '.png')
        self.write_to_textbrowser('VI Image saved at ./images/my_vistream-' + str(frame_num) + '.png')
    
    def start_ir_save(self):
        filename = self.image_save_path + 'my_irstream-%d.' % self.frame_num + self.MODE
        self.image_result.Save(filename)
        print('IR Image saved at %s' % filename)
        self.write_to_textbrowser('IR Image saved at %s' % filename)
        self.frame_num = self.frame_num + 1
    
    def set_node(self, node_name, value):
        node = PySpin.CEnumerationPtr(self.nodemap.GetNode(node_name))
        # print(node.GetEntry(0).GetName())
        if not PySpin.IsReadable(node) or not PySpin.IsWritable(node):
            print('Unable to get ' + node_name + ' ... Aborting...')
            self.write_to_textbrowser('Unable to get ' + node_name + ' ... Aborting...')
            return False
        
        node_target_val = node.GetEntryByName(value)
        if not PySpin.IsReadable(node_target_val):
            print('Unable to set ' + node_name + ' ... Aborting...')
            self.write_to_textbrowser('Unable to set ' + node_name + ' ... Aborting...')
            return False
        
        node.SetIntValue(node_target_val.GetValue())
        # print(node_name + " is set as " + value)
        return True
    
    def acquire_images(self):
        self.handle_focus() 
        try:
            self.image_result = self.cam.GetNextImage(1000)
            if self.image_result.IsIncomplete():
                print('Image incomplete with image status %d ...' % self.image_result.GetImageStatus())
                self.write_to_textbrowser('Image incomplete with image status %d ...' % self.image_result.GetImageStatus())
            else:
                if self.recording:
                    if self.MODE == 'png':
                        self.record_list.append(self.processor.Convert(self.image_result, PySpin.PixelFormat_Mono8))
                    elif self.MODE == 'raw':
                        self.record_list.append(self.processor.Convert(self.image_result, PySpin.PixelFormat_Mono16))
                
                image_data = self.image_result.GetNDArray()
                if self.MODE == 'raw':
                    image_data_ = np.array(image_data, dtype=np.uint16)
                    image_data_ = (image_data_ - image_data_.min())  / (image_data_.max() - image_data_.min()) * 255
                    image_data = image_data_.clip(0, 255).astype(np.uint8)
                frame = QtGui.QImage(image_data, 640, 480, QtGui.QImage.Format_Grayscale8)
                pix = QtGui.QPixmap.fromImage(frame)
                self.item = QGraphicsPixmapItem(pix)
                self.scene = QGraphicsScene()
                self.scene.addItem(self.item)
                self.graphicsView_1.setScene(self.scene)
                
                if self.frame_delay > 0:
                    self.frame_delay = self.frame_delay - 1
                elif self.frame_delay == 0:
                    self.start_ir_save()
                    self.frame_delay = -1
                    
            self.image_result.Release()

        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            self.write_to_textbrowser('Error: %s' % ex)
            return False
    
    def format_png(self):
        if self.streaming:
            print('can not set format while streaming!')
            self.write_to_textbrowser('can not set format while streaming!')
            if self.MODE == 'png':
                self.radioButton_1.setChecked(True)
            elif self.MODE == 'raw':
                self.radioButton_2.setChecked(True)
            return
        else:
            if self.radioButton_1.isChecked():
                self.MODE = 'png'
                print('Image format is png')
                self.write_to_textbrowser('Image format is png')
            
    def format_raw(self):
        if self.streaming:
            print('can not set format while streaming!')
            self.write_to_textbrowser('can not set format while streaming!')
            
            if self.MODE == 'png':
                self.radioButton_1.setChecked(True)
            elif self.MODE == 'raw':
                self.radioButton_2.setChecked(True)
            return
        else:
            if self.radioButton_2.isChecked():
                self.MODE = 'raw'
                print('Image format is raw')
                self.write_to_textbrowser('Image format is raw')
    
    def control_start(self):
        if self.streaming:
            print("streaming is already started!")
            self.write_to_textbrowser("streaming is already started!")
            return
        self.vis_thread = threading.Thread(target=self.run_video)
        self.vis_thread.start()
        self.vis_thread.join()
        
        self.system = PySpin.System.GetInstance()
        cam_list = self.system.GetCameras()
        num_cameras = cam_list.GetSize()
        
        if num_cameras == 0:
            cam_list.Clear()
            self.system.ReleaseInstance()
            print('Not enough cameras!')
            self.write_to_textbrowser('Not enough cameras!')
            return False

        self.cam = cam_list[0]
        self.cam.Init()
        print('init done')
        self.write_to_textbrowser('init done')

        self.nodemap = self.cam.GetNodeMap()
        self.streaming = True
        
        # self.cam.EndAcquisition()
        
        self.set_node('ImageAdjustMode', 'Auto')
        self.set_node('NUCMode', 'Automatic')
        self.set_node('NoiseReduction', 'On')
            
        sNodemap = self.cam.GetTLStreamNodeMap()
        node = PySpin.CEnumerationPtr(sNodemap.GetNode('StreamBufferHandlingMode'))
        node_target_val = node.GetEntryByName('NewestOnly')
        node.SetIntValue(node_target_val.GetValue())
        
        self.set_node('VideoSourceSelector', 'IR')
        self.set_node('ImageMode', 'Thermal')

        if self.MODE == 'raw':
            self.set_node('PixelFormat', 'Mono16')
        elif self.MODE == 'png':
            self.set_node('PixelFormat', 'Mono8')
        
        self.setMask(self.pixmap_transparent.mask())
        print('streaming...')
        self.write_to_textbrowser('streaming...')
        try:
            self.set_node('AcquisitionMode', 'Continuous')
            self.cam.BeginAcquisition()
        except PySpin.SpinnakerException as ex:
            print('Error: %s' % ex)
            self.write_to_textbrowser('Error: %s' % ex)
            
        self.processor = PySpin.ImageProcessor()
        self.processor.SetColorProcessing(PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_NONE)
        self.timer.start(40)

    
    def control_stop(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        if self.frame_delay > 0:
            print("please wait for the saving process and try again!")
            self.write_to_textbrowser("please wait for the saving process and try again!")
            return
        self.setMask(self.pixmap_white.mask())
        image_data = np.ones([480, 640], dtype=np.uint8) * 255
        frame = QtGui.QImage(image_data, 640, 480, QtGui.QImage.Format_Grayscale8)
        pix = QtGui.QPixmap.fromImage(frame)
        self.item = QGraphicsPixmapItem(pix)
        self.scene = QGraphicsScene()
        self.scene.addItem(self.item)
        self.graphicsView_1.setScene(self.scene)
        
        self.cam.EndAcquisition()
        self.streaming = False
        self.timer.stop()
        
        os.kill(self.pid1.pid, signal.SIGINT)
        
        self.cam.DeInit()
        del self.cam
        self.system.ReleaseInstance()

        print("shutdown...")
        self.write_to_textbrowser("shutdown...")
        
    def control_save(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        if self.frame_delay > 0:
            print("press too quick! please wait for the previous frame to finish saving!")
            self.write_to_textbrowser("press too quick! please wait for the previous frame to finish saving!")
            return
        self.thread_pool.submit(self.start_vi_save, self.frame_num)
        self.frame_delay = self.frame_delay_const
    
    def save_record(self):
        path = self.video_save_path + str(self.record_index) + '/'
        while os.path.exists(path):
            self.record_index = self.record_index + 1
            path = self.video_save_path + str(self.record_index) + '/'
        if not os.path.exists(path):
            os.makedirs(path)
        frame_num = 0
        for i in range(len(self.record_list)):
            filename = path + '/sequence-%d.' % frame_num + self.MODE
            self.record_list[i].Save(filename)
            frame_num = frame_num + 1
        print('Image sequence of ' + str(len(self.record_list)) + ' saved at ' + path)
        self.write_to_textbrowser('Image sequence of ' + str(len(self.record_list)) + ' saved at ' + path)
        self.record_index = self.record_index + 1
        self.record_list = []
    
    def control_record(self):
        if not self.recording:
            print('start recording')
            self.write_to_textbrowser("start recording")
            self.recording = True
            self.pushButton_13.setText("finish")
            
        elif self.recording:
            self.thread_pool.submit(self.save_record)
            self.recording = False
            self.pushButton_13.setText("record")
    
    def control_exit(self):
        if self.streaming:
            print("can not exit while streaming!")
            self.write_to_textbrowser("can not exit while streaming!")
            return
        app.quit()
        self.close()
    
    def closeEvent(self, event):
        if self.streaming:
            print("can not exit while streaming!")
            self.write_to_textbrowser("can not exit while streaming!")
            return
        app.quit()
        self.close()
        
    def handle_focus(self):
        if not self.focusing:
            return
        if self.focusing and self.focus_count < self.FOCUS_STEP:
            self.focus_count = self.focus_count + 1
        elif self.focusing and self.focus_count == self.FOCUS_STEP:
            self.set_node('FocusDirection', 'Stop')
            self.focus_count = 0
            self.focusing = False
            print('done')
            self.write_to_textbrowser('done')
        
    def focus_further(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        print('focus further...  ', end='')
        self.write_to_textbrowser('focus further...  ')
        self.set_node('FocusDirection', 'Far')
        self.focus_count = self.focus_count + 1
        self.focusing = True
            
    def focus_closer(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        print('focus closer...   ', end='')
        self.write_to_textbrowser('focus closer...   ')
        self.set_node('FocusDirection', 'Near')
        self.focus_count = self.focus_count + 1
        self.focusing = True

    def nuc_on(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        self.set_node('NUCMode', 'Automatic')
        print('NUCMode: ' + 'Automatic')
        self.write_to_textbrowser('NUCMode: ' + 'Automatic')
    
    def nuc_off(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        self.set_node('NUCMode', 'Off')
        print('NUCMode: ' + 'Off')
        self.write_to_textbrowser('NUCMode: ' + 'Off')
    
    def noise_reduce_on(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        self.set_node('NoiseReduction', 'On')
        print('NoiseReduction: ' + 'On')
        self.write_to_textbrowser('NoiseReduction: ' + 'On')
    
    def noise_reduce_off(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        self.set_node('NoiseReduction', 'Off')
        print('NoiseReduction: ' + 'Off')
        self.write_to_textbrowser('NoiseReduction: ' + 'Off')
    
    def adjst_on(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        self.set_node('ImageAdjustMode', 'Auto')
        print('ImageAdjustMode: ' + 'Auto')
        self.write_to_textbrowser('ImageAdjustMode: ' + 'Auto')
    
    def adjust_off(self):
        if not self.streaming:
            print("streaming is not started!")
            self.write_to_textbrowser("streaming is not started!")
            return
        self.set_node('ImageAdjustMode', 'Manual')
        print('ImageAdjustMode: ' + 'Manual')
        self.write_to_textbrowser('ImageAdjustMode: ' + 'Manual')

if __name__ == "__main__":
    app = QApplication(sys.argv)
    myWin = MyMainForm()
    myWin.show()
    sys.exit(app.exec_())