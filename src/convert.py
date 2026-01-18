import os
from PIL import Image

INPUT_FOLDER = "symbols"          # Endre til mappen med ikonene dine
OUTPUT_FOLDER = "output_bw"     # Mappen hvor resultatet lagres
THRESHOLD = 180                 # Juster for hvor "lyst" bildet må være for å bli hvitt

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

for file in os.listdir(INPUT_FOLDER):
    if file.lower().endswith(".png"):
        img_path = os.path.join(INPUT_FOLDER, file)
        img = Image.open(img_path)

        # Konverter til gråtoner
        img_gray = img.convert("L")

        # Konverter gråtoner til ren svart/hvitt (binary)
        img_bw = img_gray.point(lambda x: 0 if x > THRESHOLD else 1, '1')

        # Lagre nytt bilde
        output_path = os.path.join(OUTPUT_FOLDER, file)
        img_bw.save(output_path)

        print(f"Konvertert: {file}")
