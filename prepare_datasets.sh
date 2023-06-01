#!/bin/bash

dataset_name='camus_80_10_10'
version=''

source /mnt/Enterprise/miccai_2023_CRIS/CRIS.pytorch/.venv/bin/activate
cd datasets

python ../tools/folder2lmdb.py -j anns/$dataset_name$version/train.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name$version
python ../tools/folder2lmdb.py -j anns/$dataset_name$version/val.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name$version
python ../tools/folder2lmdb.py -j anns/$dataset_name$version/testA.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name$version
python ../tools/folder2lmdb.py -j anns/$dataset_name$version/testB.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name$version
