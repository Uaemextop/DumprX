#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
import math
import argparse
import sys

try:
    import requests
except ImportError:
    print("Error: 'requests' module is required. Install with: pip install requests")
    sys.exit(1)

try:
    import clint
    HAS_CLINT = True
except ImportError:
    HAS_CLINT = False

try:
    import humanize
    HAS_HUMANIZE = True
except ImportError:
    HAS_HUMANIZE = False

mirror_url = r"https://androidfilehost.com/libs/otf/mirrors.otf.php"
url_matchers = [
    re.compile(r"fid=(?P<id>\d+)")
]

class Mirror:
    def __init__(self, **entries):
        self.__dict__.update(entries)

def download_file(url, fname, fsize):
    dat = requests.get(url, stream=True)
    dat.raise_for_status()
    downloaded = 0
    with open(fname, 'wb') as f:
        if HAS_CLINT:
            bar = clint.textui.progress.bar(dat.iter_content(chunk_size=4096),
                                            expected_size=math.floor(fsize / 4096) + 1)
            for chunk in bar:
                f.write(chunk)
                f.flush()
        else:
            for chunk in dat.iter_content(chunk_size=4096):
                f.write(chunk)
                downloaded += len(chunk)
                pct = (downloaded / fsize * 100) if fsize > 0 else 0
                print('\rDownloading: {:.1f}%'.format(pct), end='', flush=True)
            print()

def get_file_info(url):
    data = requests.head(url)
    data.raise_for_status()
    rsize = int(data.headers.get('Content-Length', 0))
    if HAS_HUMANIZE:
        size = humanize.naturalsize(rsize, binary=True)
    else:
        size = '{:.1f} MB'.format(rsize / (1024 * 1024))

    # Parse Content-Disposition header without deprecated cgi module
    disposition = data.headers.get('Content-Disposition', '')
    fname = 'download'
    if 'filename=' in disposition:
        match = re.search(r'filename[*]?=["\']?([^"\';\s]+)', disposition)
        if match:
            fname = match.group(1)

    return (rsize, size, fname)

def download_servers(fid):
    cook = requests.get("https://androidfilehost.com/?fid={}".format(fid))
    post_data = {
        "submit": "submit",
        "action": "getdownloadmirrors",
        "fid": fid
    }
    mirror_headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://androidfilehost.com/?fid={}".format(fid),
        "X-MOD-SBB-CTYPE": "xhr",
        "X-Requested-With": "XMLHttpRequest"
    }
    mirror_data = requests.post(mirror_url,
                                headers=mirror_headers,
                                data=post_data,
                                cookies=cook.cookies)
    try:
        mirror_json = json.loads(mirror_data.text)
        if not mirror_json["STATUS"] == "1" or not mirror_json["CODE"] == "200":
            return None
        else:
            mirror_opts = []
            for mirror in mirror_json["MIRRORS"]:
                mirror_opts.append(Mirror(**mirror))
            return mirror_opts
    except (json.JSONDecodeError, KeyError):
        return None

def match_url(url):
    for pattern in url_matchers:
        res = pattern.search(url)
        if res is not None:
            return res
    return None

def main(link=None):
    given_url = link
    if not link:
        given_url = input("Provide an AndroidFileHost URL: ")
    file_match = match_url(given_url)
    if file_match:
        file_id = file_match.group('id')
        print("Obtaining available download servers...")
        servers = download_servers(file_id)
        if servers is None:
            print("Unable to retrieve download servers, you have probably been rate limited.")
            return
        svc = len(servers) - 1
        for idx, server in enumerate(servers):
            print('{}: {}'.format(idx, server.name))
        choice = "0"
        if not link:
            choice = input("Choose a server to download from (0-{}): ".format(svc))
        while not choice.isdigit() or int(choice) > svc or int(choice) < 0:
            choice = input("Not a valid input, choose again: ")
        server = servers[int(choice)]
        print("Downloading from {}...".format(server.name))
        rsize, size, fname = get_file_info(server.url)
        print("Size: {} | Filename: {}".format(size, fname))
        download_file(server.url, fname, rsize)
        print("Downloading complete!")
    else:
        print("This does not appear to be a supported link.")

def entry_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interactive", action="store_true", default=False,
                        help="Run afh-dl in interactive mode.")
    parser.add_argument("-l", "--link", action="store", nargs="?", type=str, default=None,
                        help="Link that should be downloaded.")
    parsed = parser.parse_args()
    if parsed.interactive:
        main()
    elif parsed.link is not None:
        main(parsed.link)
    else:
        print("A link must be specified if not in interactive mode.")

if __name__ == '__main__':
    entry_main()
