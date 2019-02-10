import sys
import os
import argparse
import logging
import time
from shutil import copyfile
from multiprocessing import Pool, Value, Lock

import openslide

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../../')

parser = argparse.ArgumentParser(description='Generate patches from a given '
                                 'list of coordinates')
parser.add_argument('wsi_path', default=None, metavar='WSI_PATH', type=str,
                    help='Path to the input directory of WSI files')
parser.add_argument('coords_path', default=None, metavar='COORDS_PATH',
                    type=str, help='Path to the input list of coordinates')#包含patch中心坐标的txt文件 比如 tumor—train.txt
parser.add_argument('patch_path', default=None, metavar='PATCH_PATH', type=str,
                    help='Path to the output directory of patch images')
parser.add_argument('--patch_size', default=768, type=int, help='patch size, '
                    'default 768')
parser.add_argument('--level', default=0, type=int, help='level for WSI, to '
                    'generate patches, default 0')
parser.add_argument('--num_process', default=5, type=int,
                    help='number of mutli-process, default 5')

count = Value('i', 0)
lock = Lock()


def process(opts):
    i, pid, x_center, y_center, args = opts
    x = int(int(x_center) - args.patch_size / 2)
    y = int(int(y_center) - args.patch_size / 2)
    wsi_path = os.path.join(args.wsi_path, pid + '.tif')
    slide = openslide.OpenSlide(wsi_path)
    img = slide.read_region(
        (x, y), args.level,
        (args.patch_size, args.patch_size)).convert('RGB')

    img.save(os.path.join(args.patch_path, str(i) + '.png'))

    global lock
    global count

    with lock:
        count.value += 1
        if (count.value) % 100 == 0:
            logging.info('{}, {} patches generated...'
                         .format(time.strftime("%Y-%m-%d %H:%M:%S"),
                                 count.value))


def run(args):
    logging.basicConfig(level=logging.INFO)
    #判断patch保存路径是否存在
    if not os.path.exists(args.patch_path):
        os.mkdir(args.patch_path)
    #shutil里面的 copyfile  将tumor_train.txt复制到 新的文件夹下的list.txt
    copyfile(args.coords_path, os.path.join(args.patch_path, 'list.txt'))

    opts_list = []
    infile = open(args.coords_path)
    for i, line in enumerate(infile):  
        pid, x_center, y_center = line.strip('\n').split(',')#对每一行 取 tumor的名字， x y坐标
        opts_list.append((i, pid, x_center, y_center, args))  #将序号 坐标计入 list里面
    infile.close()  #打开的文件关闭
    #调用多进程  # 第一个参数是函数，第二个参数是一个迭代器，将迭代器中的数字作为参数依次传入函数中
    pool = Pool(processes=args.num_process)#processes：使用的工作进程的数量  
    pool.map(process, opts_list)   #调用process函数 参数为 opts_list


def main():
    args = parser.parse_args()
    run(args)


if __name__ == '__main__':
    main()
