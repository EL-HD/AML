import json
import urllib.request
import os

with open('/Users/hobeddiaz/.gemini/antigravity/brain/ccddecea-1df3-44f5-86b8-a0f35cf91cf5/.system_generated/steps/25/output.txt', 'r') as f:
    # skip any preamble
    content = f.read()

start_idx = content.find('{"name":"projects/')
# it's usually inside [ ... ] or directly {
if start_idx != -1:
    # find [ before this
    list_start = content.rfind('[', 0, start_idx)
    if list_start != -1:
        data = json.loads(content[list_start:])
    else:
        # just find the end
        data = [json.loads("{" + content[start_idx:].split("\n")[0].strip())] # hacky
        # Wait, the output is actually JSON starting right after the timestamps
        lines = content.split('\n')
        json_str = ""
        for line in lines:
            if line.startswith('[') or line.startswith('{'):
                json_str = line
                break
        data = json.loads(json_str)

else:
    print("Could not find JSON data")
    exit(1)

os.makedirs('stitch_design_assets', exist_ok=True)

for item in (data if isinstance(data, list) else [data]):
    title = item.get('title', 'Untitled').replace(' ', '_').replace('/', '_')
    print(f"Downloading {title}...")
    
    # Download HTML
    html_url = item.get('htmlCode', {}).get('downloadUrl')
    if html_url:
        req = urllib.request.Request(html_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with open(f"stitch_design_assets/{title}.html", 'wb') as f:
                f.write(response.read())
            
    # Download Image
    img_url = item.get('screenshot', {}).get('downloadUrl')
    if img_url:
        req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with open(f"stitch_design_assets/{title}.png", 'wb') as f:
                f.write(response.read())

print("Download complete.")
