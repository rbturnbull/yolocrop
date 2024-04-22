from pathlib import Path
from PIL import Image
from appdirs import user_cache_dir
from typing import Union
import hashlib
import urllib.request
import gzip, shutil
import typer

app = typer.Typer()

class DownloadError(Exception):
    pass


def get_cached_path(filename: str, cache_dir:Path=None) -> Path:
    cache_dir = cache_dir or Path(user_cache_dir("hespi"))
    cache_dir.mkdir(exist_ok=True, parents=True)
    return cache_dir / filename


def cached_download(url: str, local_path: Union[str, Path], force: bool = False) -> None:
    """
    Downloads a file if a local file does not already exist.

    Args:
        url (str): The url of the file to download.
        local_path (str, Path): The local path of where the file should be.
            If this file isn't there or the file size is zero then this function downloads it to this location.
        force (bool): Whether or not the file should be forced to download again even if present in the local path.
            Default False.

    Raises:
        DownloadError: Raises an exception if it cannot download the file.
        IOError: Raises an exception if the file does not exist or is empty after downloading.
    """
    local_path = Path(local_path)
    if (not local_path.exists() or local_path.stat().st_size == 0) or force:
        try:
            print(f"Downloading {url} to {local_path}")
            urllib.request.urlretrieve(url, local_path)
        except:
            raise DownloadError(f"Error downloading {url}")

    if not local_path.exists() or local_path.stat().st_size == 0:
        raise IOError(f"Error reading {local_path}")


def get_stem_extension(name):
    extension_location = name.rfind(".")
    if extension_location > 0:
        name_stem = name[:extension_location]
        extension = name[extension_location:]
    else:
        name_stem = name
        extension = ".dat"

    return name_stem, extension


def get_location(location:Union[str,Path], force:bool=False, cache_dir=None) -> Path:
    location = str(location)
    if location.startswith("http"):
        name_stem, extension = get_stem_extension(location.split("/")[-1])
        url_hash = hashlib.md5(location.encode()).hexdigest()

        # gunzip if necessary
        if extension == ".gz":
            name_stem, extension = get_stem_extension(name_stem)
            local_path_gz = get_cached_path(f"{name_stem}-{url_hash}{extension}.gz", cache_dir=cache_dir)
            local_path = get_cached_path(f"{name_stem}-{url_hash}{extension}", cache_dir=cache_dir)

            if not local_path.exists() or force:
                cached_download(location, local_path_gz, force=force)
                
                #https://stackoverflow.com/a/48466691
                with gzip.open(local_path_gz, 'r') as f_in, open(local_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
                
                assert local_path.exists()
                local_path_gz.unlink()
        else:
            local_path = get_cached_path(f"{name_stem}-{url_hash}{extension}", cache_dir=cache_dir)
            cached_download(location, local_path, force=force)
    else:
        local_path = Path(location)
    
    if not local_path.exists() or local_path.stat().st_size == 0:
        raise IOError(f"Cannot read file {local_path}")

    return local_path


@app.command()
def yolocrop(weights:Path, image:Path, output:Path, res:int=1280, force:bool=False):
    """ 
    Use a YOLO model to just predict the bounding box of an object and crop it.
    
    Designed for images where there is only a single object of interest.
    """
    from ultralytics import YOLO

    weights = get_location(weights, force=force)
    model = YOLO(weights)

    results = model.predict(source=[image], show=False, save=False, imgsz=res)

    assert len(results) == 1
    predictions = results[0]

    output.parent.mkdir(exist_ok=True, parents=True)

    # find box with highest confidence
    best_confidence = 0
    best_boxes = None
    for boxes in predictions.boxes:
        confidence = boxes.conf.item()
        if confidence > best_confidence:
            best_boxes = boxes
            best_confidence = confidence

    if best_boxes:
        assert len(best_boxes.xyxy) == 1
        x0, y0, x1, y1 = best_boxes.xyxy.cpu().numpy()[0]

        # open image
        im = Image.open(image)
        im_crop = im.crop((x0, y0, x1, y1))

        im_crop.convert('RGB').save(output)


if __name__ == "__main__":
    app()