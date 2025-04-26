#!/bin/bash

cd /home/code/2025/iwaratv-autoDownload
/root/anaconda3/envs/iwaraTvAuto/bin/python app.py && echo "running successd!" >> /home/code/2025/iwaratv-autoDownload/running.log 2>&1
