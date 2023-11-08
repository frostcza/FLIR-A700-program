clc;
clear;

width=640;
height=480;
format = 'uint16';

% filename='E:\FLIR A700\python\spinnaker_python\Examples\my_demo\images\my_irstream-1.raw';
filename='E:\FLIR A700\python\spinnaker_python\Examples\my_demo\video\part1\sequence-0.raw';

fid=fopen(filename,'r');
img=fread(fid,[width,height],'uint16');
img=img';
fclose(fid);

minval = double(min(min(img)));
maxval = double(max(max(img)));
range = maxval-minval;

target = 255 * (double(img) - minval) / range + 0;

% target = double(img) - minval;

figure();
imshow(uint8(target));
title('raw image');