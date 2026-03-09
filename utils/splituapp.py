#!/usr/bin/env python3

# splituapp for Python3 by SuperR. @XDA
#
# For extracting img files from UPDATE.APP

# Based on the app_structure file in split_updata.pl by McSpoon

import os
import sys
import string
import struct
from subprocess import check_output, CalledProcessError

def extract(source, flist):
    def cmd(command):
        try:
            result = check_output(command)
            return result.strip().decode()
        except (CalledProcessError, FileNotFoundError):
            return ''

    bytenum = 4
    outdir = 'output'
    img_files = []

    os.makedirs(outdir, exist_ok=True)

    if not os.path.isfile(source):
        print('ERROR: Source file "{}" not found'.format(source))
        return 1

    with open(source, 'rb') as f:
        while True:
            i = f.read(bytenum)

            if not i:
                break
            elif i != b'\x55\xAA\x5A\xA5':
                continue

            headersize = f.read(bytenum)
            headersize = struct.unpack('<L', headersize)[0]
            f.seek(16, 1)
            filesize = f.read(bytenum)
            filesize = struct.unpack('<L', filesize)[0]
            f.seek(32, 1)
            filename = f.read(16)

            try:
                filename = filename.decode()
                filename = ''.join(c for c in filename if c in string.printable).lower()
            except UnicodeDecodeError:
                filename = ''

            f.seek(22, 1)
            crcdata = f.read(headersize - 98)

            if not flist or filename in flist:
                if filename in img_files:
                    filename = filename + '_2'

                print('Extracting ' + filename + '.img ...')

                chunk = 10240

                try:
                    if os.path.exists(os.path.join(outdir, filename + ".img")):
                        i = 1
                        while os.path.exists(os.path.join(outdir, filename + '_' + str(i) + '.img')):
                            i += 1

                        with open(os.path.join(outdir, filename + '_' + str(i) + '.img'), 'wb') as o:
                            while filesize > 0:
                                if chunk > filesize:
                                    chunk = filesize
                                o.write(f.read(chunk))
                                filesize -= chunk

                    else:
                        with open(os.path.join(outdir, filename + '.img'), 'ab') as o:
                            while filesize > 0:
                                if chunk > filesize:
                                    chunk = filesize
                                o.write(f.read(chunk))
                                filesize -= chunk
                except IOError as e:
                    print('ERROR: Failed to create {}.img: {}'.format(filename, e))
                    return 1

                img_files.append(filename)

                if os.name != 'nt':
                    if os.path.isfile('crc'):
                        print('Calculating crc value for ' + filename + '.img ...')

                        crcval = ''.join('%02X' % b for b in crcdata)
                        crcact = cmd(['./crc', 'output/' + filename + '.img'])

                        if crcval != crcact:
                            print('ERROR: crc value for ' + filename + '.img does not match')
                            return 1
            else:
                f.seek(filesize, 1)

            xbytes = bytenum - f.tell() % bytenum
            if xbytes < bytenum:
                f.seek(xbytes, 1)

    print('\nExtraction complete')
    return 0

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Split UPDATE.APP file into img files", add_help=False)
    required = parser.add_argument_group('Required')
    required.add_argument("-f", "--filename", required=True, help="Path to update.app file")
    optional = parser.add_argument_group('Optional')
    optional.add_argument("-h", "--help", action="help", help="show this help message and exit")
    optional.add_argument("-l", "--list", nargs="*", metavar=('img1', 'img2'), help="List of img files to extract")
    args = parser.parse_args()

    sys.exit(extract(args.filename, args.list))
