import os

import numpy as np
from torch.utils.data import Dataset
from PIL import Image

np.random.seed(0)

from torchvision import transforms  # noqa

from wsi.data.annotation import Annotation  # noqa


class GridImageDataset(Dataset):
    """
    Data producer that generate a square grid, e.g. 3x3, of patches and their
    corresponding labels from pre-sampled images.
    """
    def __init__(self, data_path, json_path, img_size, patch_size,
                 crop_size=224, normalize=True):
        """
        Initialize the data producer.

        Arguments:
            data_path: string, path to pre-sampled images using patch_gen.py   #切割好的图片 里面有序号 
            json_path: string, path to the annotations in json format          #标签注释文件 里面主要是每一个多边形里的节点
            img_size: int, size of pre-sampled images, e.g. 768
            patch_size: int, size of the patch, e.g. 256
            crop_size: int, size of the final crop that is feed into a CNN,
                e.g. 224 for ResNet
            normalize: bool, if normalize the [0, 255] pixel values to [-1, 1],
                mostly False for debuging purpose
        """
        self._data_path = data_path
        self._json_path = json_path
        self._img_size = img_size
        self._patch_size = patch_size
        self._crop_size = crop_size
        self._normalize = normalize
        self._color_jitter = transforms.ColorJitter(64.0/255, 0.75, 0.25, 0.04)
        self._preprocess()

    def _preprocess(self):
        if self._img_size % self._patch_size != 0:
            raise Exception('Image size / patch size != 0 : {} / {}'.
                            format(self._img_size, self._patch_size))

        self._patch_per_side = self._img_size // self._patch_size
        self._grid_size = self._patch_per_side * self._patch_per_side

        self._pids = list(map(lambda x: x.strip('.json'),   #将self._json_path里面的 每一个地址元素里面的.json删除 剩下的是slide的名字 形成一个list
                              os.listdir(self._json_path)))

        self._annotations = {}
        for pid in self._pids:#每一个pid是每一个slide的名字类似Normal_001
            pid_json_path = os.path.join(self._json_path, pid + '.json')
            anno = Annotation()
            anno.from_json(pid_json_path)
            self._annotations[pid] = anno  #为每一个slide构建一个类 并且将这些类保存到self._annotations[pid]里面

        self._coords = []   #这是将一个txt里面的所有的点 都放在这个list里面 但是感觉这个和 Annotation类重合了
        f = open(os.path.join(self._data_path, 'list.txt'))#难道每一个切割图片的文件夹下都有一个list.txt??  有 就是切割前的tumor——train.txt
        for line in f:
            pid, x_center, y_center = line.strip('\n').split(',')[0:3]
            x_center, y_center = int(x_center), int(y_center)
            self._coords.append((pid, x_center, y_center))
        f.close()

        self._num_image = len(self._coords)

    def __len__(self):
        return self._num_image

    def __getitem__(self, idx):#iter迭代的时候用到的
        pid, x_center, y_center = self._coords[idx]  #取出一个点之后 求总共的9个 来形成一个slide
        #求左上角
        x_top_left = int(x_center - self._img_size / 2)
        y_top_left = int(y_center - self._img_size / 2)
        #根据一个slide几个patch来形成一个标签网格
        # the grid of labels for each patch
        label_grid = np.zeros((self._patch_per_side, self._patch_per_side),
                              dtype=np.float32)
        for x_idx in range(self._patch_per_side):
            for y_idx in range(self._patch_per_side):
                # (x, y) is the center of each patch
                x = x_top_left + int((x_idx + 0.5) * self._patch_size)
                y = y_top_left + int((y_idx + 0.5) * self._patch_size)

                if self._annotations[pid].inside_polygons((x, y), True):#判断这个patch是否在区域里面 如果是则贴1  
                    label = 1
                else:
                    label = 0

                # extracted images from WSI is transposed with respect to
                # the original WSI (x, y)
                label_grid[y_idx, x_idx] = label

        img = Image.open(os.path.join(self._data_path, '{}.png'.format(idx))) #图片只打开这一个

        # color jitter
        img = self._color_jitter(img)

        # use left_right flip
        if np.random.rand() > 0.5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
            label_grid = np.fliplr(label_grid)

        # use rotate
        num_rotate = np.random.randint(0, 4)
        img = img.rotate(90 * num_rotate)
        label_grid = np.rot90(label_grid, num_rotate)

        # PIL image:   H x W x C
        # torch image: C X H X W
        img = np.array(img, dtype=np.float32).transpose((2, 0, 1))

        if self._normalize:
            img = (img - 128.0)/128.0

        # flatten the square grid
        img_flat = np.zeros(
            (self._grid_size, 3, self._crop_size, self._crop_size),# 9*3*224*224
            dtype=np.float32)
        label_flat = np.zeros(self._grid_size, dtype=np.float32)

        idx = 0      #从每一个256里面 切出来224的大小
        for x_idx in range(self._patch_per_side):
            for y_idx in range(self._patch_per_side):
                # center crop each patch
                x_start = int(
                    (x_idx + 0.5) * self._patch_size - self._crop_size / 2)#crop_size是224  （0+0.5）*256-224/2=128-112=16
                x_end = x_start + self._crop_size  #16+224=240
                y_start = int(
                    (y_idx + 0.5) * self._patch_size - self._crop_size / 2)
                y_end = y_start + self._crop_size
                img_flat[idx] = img[:, x_start:x_end, y_start:y_end]
                label_flat[idx] = label_grid[x_idx, y_idx]

                idx += 1

        return (img_flat, label_flat)
