from __future__ import unicode_literals

import logging
import ntpath
import os
import os.path
import subprocess
import sys
import time

from os.path import isdir
from os.path import isfile

import psutil
import tornado
import tornado.autoreload
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web

from tornado.options import define
from tornado.options import options

import decorators


logger = logging.getLogger(__name__)


ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_ROOT = os.path.join(ROOT, u'templates')
STATIC_ROOT = os.path.join(ROOT, u'static')


define(u'port', default=8000, help=u'Run server on the given port.', type=int)
define(u'media_root', default=u'/mnt/diskstation/video',
    help=u'Directory where media folder is located.', type=str)


class BaseHandler(tornado.web.RequestHandler):
    """BaseHandler that all handlers inherit from."""


class BrowseHandler(BaseHandler):
    """Handler for browsing directories."""

    @tornado.web.asynchronous
    def get(self, path=u''):
        logger.info("====== Default ENCODING: {} / {} ======".format(
                sys.getfilesystemencoding(), os.path.expandvars('$LC_CTYPE')))
        dirpath = (os.path.join(options.media_root, path)
                if path else options.media_root)
        if not isdir(dirpath):
            raise tornado.web.HTTPError(404)
        files = [f for f in os.listdir(dirpath)
                if isfile(os.path.join(dirpath, f))]
        directories = [d for d in os.listdir(dirpath)
                if isdir(os.path.join(dirpath, d))]
        self.render(u'browse.html', relpath=path, dirpath=dirpath,
                files=files, directories=directories)


class Control(object):
    """Object defining player controls."""

    def __init__(self, cmd, post_processing=None):
        self.cmd = cmd
        self.post_processing = (post_processing
                if post_processing else (lambda: None))


class PlayerHandler(BaseHandler):
    """Handler to display player with controls for videos."""

    @tornado.web.asynchronous
    def get(self, filepath):
        if not isfile(os.path.join(options.media_root, filepath)):
            raise tornado.web.HTTPError(404)
        self.render(u'player.html', controls=self.application.control_names(),
                filepath=filepath, filename=ntpath.basename(filepath))


class ControlHandler(BaseHandler):
    """Handler to control the currently playing video."""

    @tornado.web.asynchronous
    def get(self, filepath):
        if not isfile(os.path.join(options.media_root, filepath)):
            raise tornado.web.HTTPError(404)
        control = self.get_argument(u'control', u'play')
        if not self.application.is_playing() and control == u'play':
            self.application.play(filepath)
        else:
            try:
                self.application.control(control)
            except subprocess.CalledProcessError, e:
                self.application.quit()
        self.write(dict(message=u'Executed {}'.format(control)))
        self.finish()


class RaspberryPiPlayerApplication(tornado.web.Application):
    """App to play video on Raspberry Pi."""

    def __init__(self, handlers, **settings):
        self.__is_playing = False
        self.__player_process = None
        self.__control_map = {
            u'play': Control(u'p'),
            u'pause': Control(u'p'),
            u'volume-up': Control(u'+'),
            u'volume-down': Control(u'-'),
            u'forward': Control(u'\x1B[C'),
            u'backward': Control(u'\x1B[D'),
            u'fast-forward': Control(u'\x1B[A'),
            u'fast-backward': Control(u'\x1B[B'),
            u'step-forward': Control(u'o'),
            u'step-backward': Control(u'i'),
            u'next-audio-stream': Control(u'k'),
            u'previous-audio-stream': Control(u'j'),
            u'subtitles': Control(u's'),
            u'stop': Control(u'q', post_processing=self.quit),
        }
        tornado.web.Application.__init__(self, handlers, **settings)

    def control_names(self):
        """Get list of valid control names."""
        return self.__control_map.keys()

    def is_playing(self):
        return self.__is_playing

    def play(self, filepath):
        """Start video playback."""
        self.quit()  # quit currently playback
        full_filepath = os.path.join(options.media_root, filepath)
        try:
            self.__player_process = psutil.Popen(
                    [u'omxplayer', u'-r', u'-o', u'hdmi', full_filepath],
                    stdin=subprocess.PIPE)
            subprocess.check_call(
                    [u'echo', u'.'],
                    stdout=self.__player_process.stdin)
            self.__is_playing = True
        except subprocess.CalledProcessError, e:
            self.__is_playing = False

    @decorators.playing
    def control(self, control_name):
        """Control the currently playing video."""
        control = self.__control_map.get(control_name, None)
        if control:
            subprocess.check_call(
                    [u'echo', u'-n', control.cmd],
                    stdout=self.__player_process.stdin)
            control.post_processing()
        else:
            raise Exception(u'Invalid control name {}'.format(control))

    @decorators.playing
    def quit(self):
        """Do post playback cleanup."""
        if self.__player_process:
            process = self.__player_process
            for child in process.children():
                child.terminate()
                child.wait(timeout=3)
            process.terminate()
            process.wait(timeout=3)
            self.__player_process = None
        self.__is_playing = False


settings = dict(
    template_path=TEMPLATE_ROOT,
    static_path=STATIC_ROOT
)


application = RaspberryPiPlayerApplication([
    (r'/', tornado.web.RedirectHandler, {u'url': u'/browse'}),
    (r'/browse', BrowseHandler),
    (r'/browse/(.*)', BrowseHandler),
    (r'/play/(.*)', PlayerHandler),
    (r'/control/(.*)', ControlHandler),
], **settings)


def main():
    tornado.options.parse_command_line()
    application.listen(options.port)
    ioloop = tornado.ioloop.IOLoop.instance()
    for (path, dirs, files) in os.walk(TEMPLATE_ROOT):
        for item in files:
            tornado.autoreload.watch(os.path.join(path, item))
    tornado.autoreload.start(ioloop)
    ioloop.start()


if __name__ == '__main__':
    main()
