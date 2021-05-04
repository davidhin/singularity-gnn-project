#!/bin/bash
# Get Google Drive files here
# To view drive file, go to the link:
# https://drive.google.com/file/d/<file_id>

if [[ -d storage/external ]]; then
    echo "storage exists, starting download"
else
    mkdir --parents storage/external
fi

cd storage/external

if [[ ! -d "BGNN4VD" ]]; then
    git clone https://github.com/SicongCao/BGNN4VD.git
    cd BGNN4VD
    unzip dataset.zip
    mv dataset/* .
    rm -rf dataset .git dataset.zip README.md
    cd ..
else
    echo "Already downloaded BGNN4VD dataset"
fi

if [[ ! -d "reveal_chrome_debian" ]]; then
    gdown https://drive.google.com/uc\?id\=1cU1KZnY0EnUtHdTjdm3B6guGY5R8EzM9
    unzip data.zip
    rm -rf data.zip
else
    echo "Already downloaded ReVeal data"
fi


cd ..