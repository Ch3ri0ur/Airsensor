# AIRSENSOR

Set up Service

Requirements 
Install grafana and influxdb

add service
```
chriw@raspberrypi:/lib/systemd/system $ cat airsensor.service 
[Unit]
Description=Runs script to check Airquality
After=multi-user.target

[Service]
Type=Simple
ExecStart=/home/chriw/Pimoroni/runcombair.sh
Restart=always

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl daemon-reload
sudo systemctl enable airsensor.service
```