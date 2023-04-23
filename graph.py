from datetime import datetime, timedelta
from PIL import Image, ImageFont, ImageDraw
from dataclasses import dataclass, field


# text image and rotate it so it's easy to paste in the buffer.
def draw_rotated_text(image, text, position, angle, font, fill=(255, 255, 255)):
    # Get rendered font width and height.
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width, height = right - left, bottom - top
    # Create a new image with transparent background to store the text.
    textimage = Image.new("RGBA", (width * 3, height * 3), (0, 0, 0, 0))
    # Render the text.
    textdraw = ImageDraw.Draw(textimage)
    textdraw.text((0, 0), text, font=font, fill=fill)
    # Rotate the text image.
    rotated = textimage.rotate(angle, expand=1)
    # Paste the text into the image, using it as a mask for transparency.
    image.paste(rotated, position, rotated)


def clamp(n, minn, maxn):
    return max(min(maxn, n), minn)


def score_to_color(score):
    red = score * 2
    green = (255 - score) * 2
    return (clamp(red, 0, 255), clamp(green, 0, 255), 0)


@dataclass
class rollingGraph:
    xmax: int
    ymax: int
    timemax: timedelta
    delta_per_pixel: timedelta = field(init=False)

    rolling_values: list[float] = field(default_factory=list)
    timesteps: list[int] = field(default_factory=list)
    oldest_time: datetime = field(default_factory=datetime.now)
    latest_value: int = 500

    def __post_init__(self):
        self.delta_per_pixel = self.timemax / self.ymax

    def scale_between_min_max(
        self, value, min_value, max_value, min_target=0.0, max_target=1.0, invert=True
    ):
        if value > max_value:
            return max_target if not invert else min_target
        if value < min_value:
            return min_target if not invert else max_target
        scaled_value = (value - min_value) / (max_value - min_value) * (
            max_target - min_target
        ) + min_target
        if invert:
            return max_target - scaled_value

        return scaled_value

    def graphimage(self) -> Image:
        if len(self.rolling_values) < 2:
            return Image.new("RGB", (self.xmax, self.ymax), (0, 0, 0))
        img = Image.new("RGB", (self.xmax, self.ymax), (0, 0, 0))
        tmp_rolling_values = self.rolling_values.copy()
        tmp_rolling_values.append(self.latest_value)
        max_value = max(max(tmp_rolling_values), 1000)
        min_value = min(min(tmp_rolling_values), 500)

        for x, val in enumerate(tmp_rolling_values):
            scaled_val = self.scale_between_min_max(
                val, min_value, max_value, 0, self.ymax - 1
            )

            c02_score = int(max(min((val - 500) / 500 * 255, 255), 0))
            score_color = score_to_color(c02_score)
            img.putpixel((x, int(scaled_val)), score_color)

            # paint in pixels between the last and current value

            if x > 0:
                last_val = tmp_rolling_values[x - 1]
                scaled_last_val = self.scale_between_min_max(
                    last_val, min_value, max_value, 0, self.ymax - 1
                )
                if scaled_last_val < scaled_val:
                    for y in range(int(scaled_last_val), int(scaled_val)):
                        virtual_val = self.scale_between_min_max(
                            self.ymax - y,
                            0,
                            self.ymax - 1,
                            min_value,
                            max_value,
                            invert=False,
                        )
                        c02_score = int(
                            max(min((virtual_val - 500) / 500 * 255, 255), 0)
                        )
                        score_color = score_to_color(c02_score)
                        img.putpixel((x, y), score_color)
                else:
                    for y in range(int(scaled_val), int(scaled_last_val)):
                        virtual_val = self.scale_between_min_max(
                            self.ymax - y,
                            0,
                            self.ymax - 1,
                            min_value,
                            max_value,
                            invert=False,
                        )
                        c02_score = int(
                            max(min((virtual_val - 500) / 500 * 255, 255), 0)
                        )
                        score_color = score_to_color(c02_score)
                        img.putpixel((x, y), score_color)

            font = ImageFont.load_default()
            # write in max and min values into the image
            # fstring that does not draw any decimals

            draw_rotated_text(
                img, f"{int(max_value)}", (110, 3), 0, font, fill=(255, 255, 255)
            )
            draw_rotated_text(
                img,
                f"{int(min_value)}",
                (110, self.ymax - 13),
                0,
                font,
                fill=(255, 255, 255),
            )

        return img

    def addTimestep(self, value, time):
        if self.is_buffer_full():
            # average over timesteps
            average_value = sum(self.timesteps) / len(self.timesteps)

            if len(self.rolling_values) >= self.xmax - 1:
                # remove oldest rolling_values
                self.rolling_values.pop(0)
            # add average to rolling_values
            self.rolling_values.append(average_value)

            # empty timesteps
            self.timesteps = []

        self.latest_value = value
        if not self.timesteps:
            self.oldest_time = time
        self.timesteps.append(value)

    def is_buffer_full(self):
        return (
            self.timesteps and datetime.now() - self.oldest_time > self.delta_per_pixel
        )

    def getGraph(self):
        resampled = self.resample(self.timesteps)
        return self.graphimage(resampled, self.xmax, self.ymax)
