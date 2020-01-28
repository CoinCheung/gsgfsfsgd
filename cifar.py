import os.path as osp
import pickle
import random
#  from queue import Queue
#  from threading import Thread
from multiprocessing import Process, Queue
import numpy as np
from PIL import Image

import torch
from torch.utils.data import Dataset
import torchvision
import transform as T



def load_data_train(L=250, dspth='./dataset'):
    datalist = [
        osp.join(dspth, 'cifar-10-batches-py', 'data_batch_{}'.format(i+1))
        for i in range(5)
    ]
    data, labels = [], []
    for data_batch in datalist:
        with open(data_batch, 'rb') as fr:
            entry = pickle.load(fr, encoding='latin1')
            lbs = entry['labels'] if 'labels' in entry.keys() else entry['fine_labels']
            data.append(entry['data'])
            labels.append(lbs)
    data = np.concatenate(data, axis=0)
    labels = np.concatenate(labels, axis=0)
    n_labels = L // 10
    data_x, label_x, data_u, label_u = [], [], [], []
    for i in range(10):
        indices = np.where(labels == i)[0]
        np.random.shuffle(indices)
        inds_x, inds_u = indices[:n_labels], indices[n_labels:]
        data_x += [
            data[i].reshape(3, 32, 32).transpose(1, 2, 0)
            for i in inds_x
        ]
        label_x += [labels[i] for i in inds_x]
        data_u += [
            data[i].reshape(3, 32, 32).transpose(1, 2, 0)
            for i in inds_u
        ]
        label_u += [labels[i] for i in inds_u]
    return data_x, label_x, data_u, label_u


def load_data_val(dspth='./dataset'):
    datalist = [
        osp.join(dspth, 'cifar-10-batches-py', 'test_batch')
    ]
    data, labels = [], []
    for data_batch in datalist:
        with open(data_batch, 'rb') as fr:
            entry = pickle.load(fr, encoding='latin1')
            lbs = entry['labels'] if 'labels' in entry.keys() else entry['fine_labels']
            data.append(entry['data'])
            labels.append(lbs)
    data = np.concatenate(data, axis=0)
    labels = np.concatenate(labels, axis=0)
    data = [
        el.reshape(3, 32, 32).transpose(1, 2, 0)
        for el in data
    ]
    return data, labels


class Cifar10(Dataset):
    def __init__(self, data, labels, num_imgs=None, is_train=True):
        super(Cifar10, self).__init__()
        self.data, self.labels = data, labels
        self.is_train = is_train
        self.num_imgs = num_imgs
        assert len(self.data) == len(self.labels)
        mean, std = (0.4914, 0.4822, 0.4465), (0.2471, 0.2435, 0.2616)
        if is_train:
            self.trans_weak = T.Compose([
                T.Resize((32, 32)),
                T.PadandRandomCrop(border=4, cropsize=(32, 32)),
                T.RandomHorizontalFlip(p=0.5),
                T.Normalize(mean, std),
                T.ToTensor(),
            ])
            self.trans_strong = T.Compose([
                T.Resize((32, 32)),
                T.PadandRandomCrop(border=4, cropsize=(32, 32)),
                T.RandomHorizontalFlip(p=0.5),
                T.Normalize(mean, std),
                T.ToTensor(),
            ])
        else:
            self.trans = T.Compose([
                T.Resize((32, 32)),
                T.Normalize(mean, std),
                T.ToTensor(),
            ])

    def __getitem__(self, idx):
        idx = idx % len(self.data)
        im, lb = self.data[idx], self.labels[idx]
        if self.is_train:
            return self.trans_weak(im), self.trans_weak(im), lb
        else:
            return self.trans(im), lb

    def __len__(self):
        leng = len(self.data)
        if not self.num_imgs is None:
            leng = (self.num_imgs // leng + 1) * leng
        return leng




def get_train_loader(batch_size, mu, n_iters_per_epoch, L, root='dataset'):
    data_x, label_x, data_u, label_u = load_data_train(L=L, dspth=root)

    ds_x = Cifar10(
        data=data_x,
        labels=label_x,
        num_imgs=n_iters_per_epoch * batch_size,
        is_train=True
    )
    dl_x = torch.utils.data.DataLoader(
        ds_x,
        shuffle=True,
        batch_size=batch_size,
        drop_last=True,
        num_workers=1,
        pin_memory=True
    )
    ds_u = Cifar10(
        data=data_u,
        labels=label_u,
        num_imgs=n_iters_per_epoch * batch_size * mu,
        is_train=True
    )
    dl_u = torch.utils.data.DataLoader(
        ds_u,
        shuffle=True,
        batch_size=batch_size * mu,
        drop_last=True,
        num_workers=1,
        pin_memory=True
    )
    return dl_x, dl_u


def get_val_loader(batch_size, num_workers, pin_memory=True, root='cifar10'):
    data, labels = load_data_val()
    ds = Cifar10(
        data=data,
        labels=labels,
        is_train=False
    )
    dl = torch.utils.data.DataLoader(
        ds,
        shuffle=False,
        batch_size=batch_size,
        drop_last=False,
        num_workers=num_workers,
        pin_memory=pin_memory
    )
    return dl


class OneHot(object):
    def __init__(
            self,
            n_labels,
            lb_ignore=255,
        ):
        super(OneHot, self).__init__()
        self.n_labels = n_labels
        self.lb_ignore = lb_ignore

    def __call__(self, label):
        N, *S = label.size()
        size = [N, self.n_labels] + S
        lb_one_hot = torch.zeros(size)
        if label.is_cuda:
            lb_one_hot = lb_one_hot.cuda()
        ignore = label.data.cpu() == self.lb_ignore
        label[ignore] = 0
        lb_one_hot.scatter_(1, label.unsqueeze(1), 1)
        ignore = ignore.nonzero()
        _, M = ignore.size()
        a, *b = ignore.chunk(M, dim=1)
        lb_one_hot[[a, torch.arange(self.n_labels), *b]] = 0

        return lb_one_hot


if __name__ == "__main__":
    dl_x, dl_u = get_train_loader(64, 250, 2, 2)
    dl_x2 = iter(dl_x)
    dl_u2 = iter(dl_u)
    ims, lb = next(dl_u2)
    print(type(ims))
    print(len(ims))
    print(ims[0].size())
    print(len(dl_u2))
    for i in range(1024):
        try:
            ims_x, lbs_x = next(dl_x2)
            #  ims_u, lbs_u = next(dl_u2)
            print(i, ": ", ims_x[0].size())
        except StopIteration:
            dl_x2 = iter(dl_x)
            dl_u2 = iter(dl_u)
            ims_x, lbs_x = next(dl_x2)
            #  ims_u, lbs_u = next(dl_u2)
            print('recreate iterator')
            print(i, ": ", ims_x[0].size())
