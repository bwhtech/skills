import argparse
import math

from PIL import Image, ImageDraw

RED = (229, 70, 47)
SCALE = 2


def parse_box(value):
	parts = [float(part) for part in value.split(",")]
	if len(parts) != 4:
		raise argparse.ArgumentTypeError("expected four comma-separated numbers")
	return parts


def to_output(point_x, point_y, crop):
	return (point_x - crop[0]) * SCALE, (point_y - crop[1]) * SCALE


def draw_box(draw, box, crop):
	left, top = to_output(box[0], box[1], crop)
	right, bottom = to_output(box[2], box[3], crop)
	draw.rounded_rectangle((left, top, right, bottom), radius=14, outline=RED, width=5)


def draw_arrow(draw, arrow, crop):
	start_x, start_y = to_output(arrow[0], arrow[1], crop)
	end_x, end_y = to_output(arrow[2], arrow[3], crop)
	draw.line((start_x, start_y, end_x, end_y), fill=RED, width=6)
	angle = math.atan2(end_y - start_y, end_x - start_x)
	head_length = 22
	head = [(end_x, end_y)]
	for offset in (-math.pi / 7, math.pi / 7):
		head.append(
			(
				end_x - head_length * math.cos(angle + offset),
				end_y - head_length * math.sin(angle + offset),
			)
		)
	draw.polygon(head, fill=RED)


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("source")
	parser.add_argument("target")
	parser.add_argument("--crop", type=parse_box, required=True)
	parser.add_argument("--box", type=parse_box, action="append", default=[])
	parser.add_argument("--arrow", type=parse_box, action="append", default=[])
	arguments = parser.parse_args()

	image = Image.open(arguments.source).convert("RGB").crop(tuple(int(value) for value in arguments.crop))
	image = image.resize((image.width * SCALE, image.height * SCALE), Image.LANCZOS)
	draw = ImageDraw.Draw(image)
	for box in arguments.box:
		draw_box(draw, box, arguments.crop)
	for arrow in arguments.arrow:
		draw_arrow(draw, arrow, arguments.crop)
	image.save(arguments.target)
	print(f"{arguments.target} {image.width}x{image.height}")


if __name__ == "__main__":
	main()
