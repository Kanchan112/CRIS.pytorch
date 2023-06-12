#!/bin/bash

dataset_name='kvasir_polyp_80_10_10'
version='allp'

source ./.venv/bin/activate
cd datasets
python ../tools/folder2lmdb.py -j /mnt/Enterprise/miccai_2023_CRIS/CRIS.pytorch/datasets/anns/kvasir_polyp_80_10_10/train.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name$version
python ../tools/folder2lmdb.py -j /mnt/Enterprise/miccai_2023_CRIS/CRIS.pytorch/datasets/anns/kvasir_polyp_80_10_10/val.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name$version
python ../tools/folder2lmdb.py -j /mnt/Enterprise/miccai_2023_CRIS/CRIS.pytorch/datasets/anns/kvasir_polyp_80_10_10/testA.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name$version
python ../tools/folder2lmdb.py -j /mnt/Enterprise/miccai_2023_CRIS/CRIS.pytorch/datasets/anns/kvasir_polyp_80_10_10/testB.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name$version

