# This script will run on a raspberry pi 4
# This script reads out a set of 3 air sensors from pimoroni,
# a BME688 Air Quality Sensor on i2c 0x78
# a SCD41 Full CO2 Sensor on i2c 0x62
# and a mics 6814 Gas Sensor  on i2c 0x19
# The script then takes this data and displays it on a 1.3 inc LCD colour ips lcd spi 240x240 display


import bme680  # https://github.com/pimoroni/bme680-python/blob/master/examples/indoor-air-quality.py
from mics6814 import (
    MICS6814,
    Mics6814Reading,
)  # https://github.com/pimoroni/mics6814-python/blob/master/examples/gas.py

# todo the mics has a led i could use to indicate the air quality
from scd4x import SCD4X  # https://github.com/pimoroni/scd4x-python
import ST7789  # https://github.com/pimoroni/st7789-python
from influxdb import InfluxDBClient
import time

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from datetime import datetime, timedelta
from graph import rollingGraph, draw_rotated_text, score_to_color


def main():
    lcd = ST7789.ST7789(
        port=0,
        cs=1,
        dc=9,
        backlight=12,
        rotation=90,
        spi_speed_hz=80 * 1000 * 1000,
    )
    display_type = "square"
    disp = ST7789.ST7789(
        height=135 if display_type == "rect" else 240,
        rotation=0 if display_type == "rect" else 90,
        port=0,
        cs=ST7789.BG_SPI_CS_FRONT,  # BG_SPI_CS_BACK or BG_SPI_CS_FRONT
        dc=9,
        backlight=19,  # 18 for back BG slot, 19 for front BG slot.
        spi_speed_hz=80 * 1000 * 1000,
        offset_left=0 if display_type == "square" else 40,
        offset_top=53 if display_type == "rect" else 0,
    )

    # Initialize display.
    disp.begin()

    WIDTH = disp.width
    HEIGHT = disp.height

    rollingGraph_instance = rollingGraph(WIDTH, 100, timedelta(minutes=1))

    try:
        airsensor: bme680.BME680 = bme680.BME680(bme680.I2C_ADDR_PRIMARY)
    except (RuntimeError, OSError):
        airsensor: bme680.BME680 = bme680.BME680(bme680.I2C_ADDR_SECONDARY)

    # These oversampling settings can be tweaked to
    # change the balance between accuracy and noise in
    # the data.

    airsensor.set_humidity_oversample(bme680.OS_2X)
    airsensor.set_pressure_oversample(bme680.OS_4X)
    airsensor.set_temperature_oversample(bme680.OS_8X)
    airsensor.set_filter(bme680.FILTER_SIZE_3)
    airsensor.set_gas_status(bme680.ENABLE_GAS_MEAS)

    airsensor.set_gas_heater_temperature(320)
    airsensor.set_gas_heater_duration(150)
    airsensor.select_gas_heater_profile(0)

    # start_time and curr_time ensure that the
    # burn_in_time (in seconds) is kept track of.
    start_time = time.time()
    curr_time = time.time()
    burn_in_time = 300

    burn_in_data = []

    # instanciate influxdb client
    influx_client = InfluxDBClient(host="localhost", port=8086)
    # make sure the database exists
    # influx_client.drop_database("airquality")
    # influx_client.create_database("airquality")
    influx_client.switch_database("airquality")

    try:
        # Collect gas resistance burn-in values, then use the average
        # of the last 50 values to set the upper limit for calculating
        # gas_baseline.
        print("Collecting gas resistance burn-in data for 5 mins\n")
        # while curr_time - start_time < burn_in_time:
        #     curr_time = time.time()
        #     if airsensor.get_sensor_data() and airsensor.data.heat_stable:
        #         gas = airsensor.data.gas_resistance
        #         burn_in_data.append(gas)
        #         print(f"Gas: {gas} Ohms")
        #         time.sleep(1)

        # gas_baseline = sum(burn_in_data[-50:]) / 50.0
        gas_baseline = 111182.5744372356

        # Set the humidity baseline to 40%, an optimal indoor humidity.
        hum_baseline = 40.0

        # This sets the balance between humidity and gas reading in the
        # calculation of air_quality_score (25:75, humidity:gas)
        hum_weighting = 0.25

        print(
            "Gas baseline: {0} Ohms, humidity baseline: {1:.2f} %RH\n".format(
                gas_baseline, hum_baseline
            )
        )
    except KeyboardInterrupt:
        pass
    no2sensor: MICS6814 = MICS6814()
    no2sensor.set_brightness = 1.0
    no2sensor.set_led(0, 0, 255)
    time.sleep(1)
    no2sensor.set_brightness = 1.0
    no2sensor.set_led(0, 255, 0)
    time.sleep(1)
    no2sensor.set_brightness = 1.0
    no2sensor.set_led(255, 0, 0)
    time.sleep(1)
    no2sensor.set_brightness = 0.0
    no2sensor.set_led(0, 0, 0)
    co2sensor: SCD4X = SCD4X()
    # https://github.com/pimoroni/scd4x-python/tree/main/library/tests
    co2sensor.start_periodic_measurement()
    gas_score = 0.0
    hum = 0.0
    air_quality_score = 0.0
    beforeair = time.time()

    while True:
        if beforeair:
            print(f"Air sensor took {time.time() - beforeair} seconds to read data")
        beforeair = time.time()
        if airsensor.get_sensor_data() and airsensor.data.heat_stable:
            gas = airsensor.data.gas_resistance
            gas_offset = gas_baseline - gas

            hum = airsensor.data.humidity
            hum_offset = hum - hum_baseline

            # Calculate hum_score as the distance from the hum_baseline.
            if hum_offset > 0:
                hum_score = 100 - hum_baseline - hum_offset
                hum_score /= 100 - hum_baseline
                hum_score *= hum_weighting * 100

            else:
                hum_score = hum_baseline + hum_offset
                hum_score /= hum_baseline
                hum_score *= hum_weighting * 100

            # Calculate gas_score as the distance from the gas_baseline.
            if gas_offset > 0:
                gas_score = gas / gas_baseline
                gas_score *= 100 - (hum_weighting * 100)

            else:
                gas_score = 100 - (hum_weighting * 100)

            # Calculate air_quality_score.
            air_quality_score = hum_score + gas_score

            print(
                f"Gas: {gas:.2f} Ohms,humidity: {hum:.2f} %RH,air quality: {air_quality_score:.2f}"
            )
        afterair = time.time()
        no2sensor_readings: Mics6814Reading = no2sensor.read_all()
        aftern02 = time.time()

        oxidising = no2sensor_readings.oxidising
        reducing = no2sensor_readings.reducing
        nh3 = no2sensor_readings.nh3
        adc = no2sensor_readings.adc

        co2, temp, rel_humidity, timestamp = co2sensor.measure()
        afterc02 = time.time()

        print(
            f"air: {afterair-beforeair:.2f} s, n02: {aftern02-afterair:.2f} s, c02: {afterc02-aftern02:.2f} s"
        )

        rollingGraph_instance.addTimestep(co2, datetime.now())

        # print all values
        print(
            f"oxidising: {oxidising:.2f} Ohms, reducing: {reducing:.2f} Ohms, nh3: {nh3:.2f} Ohms, adc: {adc:.2f} Ohms"
        )
        print(
            f"co2: {co2:.2f} ppm, temp: {temp:.2f} C, rel_humidity: {rel_humidity:.2f} %RH, time: {timestamp:.2f} s"
        )
        print("----------------------------------")

        # uplaod all values to influxdb
        influx_client.write_points(
            [
                {
                    "measurement": "air_quality",
                    "fields": {
                        "gas_score": gas_score,
                        "humidity": hum,
                        "air_quality_score": air_quality_score,
                        "oxidising": oxidising,
                        "reducing": reducing,
                        "nh3": nh3,
                        "adc": adc,
                        "co2": co2,
                        "temp": temp,
                        "rel_humidity": rel_humidity,
                        "time": timestamp,
                    },
                }
            ]
        )

        c02_score = int(max(min((co2 - 500) / 500 * 255, 255), 0))

        score_color = score_to_color(c02_score)
        hour = datetime.now().hour
        if 6 < hour < 22:
            disp.set_backlight(True)
            # Clear the display to a red background.
            # Can pass any tuple of red, green, blue values (from 0 to 255 each).
            # Get a PIL Draw object to start drawing on the display buffer.

            img = Image.new("RGB", (WIDTH, HEIGHT), color=score_color)
            complementory_text_color = find_complementary_text_color(score_color)
            img.paste(rollingGraph_instance.graphimage(), (0, 140))
            # draw = ImageDraw.Draw(img)
            # Load default font.
            font = ImageFont.load_default()
            font2 = ImageFont.truetype("DejaVuSans.ttf", 30)

            # Write two lines of white text on the buffer, rotated 90 degrees counter clockwise.
            draw_rotated_text(
                img, f"Temp {temp:.2f}", (20, 60), 0, font, fill=complementory_text_color
            )
            draw_rotated_text(
                img, f"Humidity {hum:.2f}", (20, 80), 0, font, fill=complementory_text_color
            )
            draw_rotated_text(
                img,
                f"Air Quality {air_quality_score:.2f}",
                (20, 100),
                0,
                font,
                fill=complementory_text_color,
            )
            draw_rotated_text(
                img, f"Time {time.ctime()}", (20, 120), 0, font, fill=complementory_text_color
            )

            draw_rotated_text(
                img, f"CO2 {co2}", (20, 20), 0, font2, fill=complementory_text_color
            )
            # Write buffer to display hardware, must be called to make things visible on the
            # display!
            disp.display(img)
        else:
            # img = Image.new("RGB", (WIDTH, HEIGHT), color=(0,0,0))

            # disp.display(img)
            disp.set_backlight(False)

def find_complementary_text_color(color):
    R, G, B = color
    return (0,0,0) if (R*0.299 + G*0.587 + B*0.114) > 186 else (255,255,255)

if __name__ == "__main__":
    main()
