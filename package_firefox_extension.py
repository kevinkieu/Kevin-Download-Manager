"""
Helper script to package Firefox extension (.zip / .xpi)
"""

import os
import zipfile

def package_firefox():
    ext_dir = os.path.abspath("kdm_extension")
    output_zip = os.path.abspath("kdm_extension_firefox.zip")
    
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(ext_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, ext_dir)
                
                # In Firefox zip, use manifest_firefox.json as manifest.json
                if file == "manifest_firefox.json":
                    z.write(full_path, "manifest.json")
                elif file == "manifest.json":
                    continue # Skip chromium manifest
                else:
                    z.write(full_path, rel_path)
                    
    print(f"[OK] Packaged Firefox extension to: {output_zip}")

if __name__ == "__main__":
    package_firefox()
