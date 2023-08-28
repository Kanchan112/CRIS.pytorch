#!/bin/bash

source /mnt/Enterprise/miccai_2023_CRIS/CRIS.pytorch/.venv/bin/activate
cd datasets

for dataset_name in 'bkai_polyp_80_10_10' 'kvasir_polyp_80_10_10' 'dfu-2022_80_10_10' 'clinicdb_polyp_80_10_10' 'isic_90_10_d' 'camus_80_10_10' 'chexlocalize_80_10_10' 'busi_80_10_10'
do 
    python ./CRIS.pytorch/tools/folder2lmdb.py -j anns/$dataset_name/train.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name
    python ./CRIS.pytorch/tools/folder2lmdb.py -j anns/$dataset_name/val.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name
    python ./CRIS.pytorch/tools/folder2lmdb.py -j anns/$dataset_name/testA.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name
    python ./CRIS.pytorch/tools/folder2lmdb.py -j anns/$dataset_name/testB.json -i images/$dataset_name/ -m masks/$dataset_name -o lmdb/$dataset_name
done
