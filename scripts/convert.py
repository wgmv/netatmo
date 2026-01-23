import os
from PIL import Image

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)  # Parent directory (project root)

INPUT_FOLDER =  os.path.join(BASE_DIR, 'assets/symbols')          # Change to the folder with your icons
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'assets/output_bw')     # The folder where the result is saved
THRESHOLD = 180                 # Adjust for how 'bright' the image must be to become white

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

for file in os.listdir(INPUT_FOLDER):
    if file.lower().endswith(".png"):
        img_path = os.path.join(INPUT_FOLDER, file)
        img = Image.open(img_path)

        # Convert to grayscale
        img_gray = img.convert("L")

        # Convert grayscale to pure black/white (binary)
        img_bw = img_gray.point(lambda x: 0 if x > THRESHOLD else 1, '1')

        # Save new image
        output_path = os.path.join(OUTPUT_FOLDER, file)
        img_bw.save(output_path)

        print(f"Converted: {file}")
