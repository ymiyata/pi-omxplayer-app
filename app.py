from __future__ import unicode_literals

import ntpath
import os
import os.path
import subprocess
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


ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_ROOT = os.path.join(ROOT, u'templates')
STATIC_ROOT = os.path.join(ROOT, u'static')


define('port', default=8222, help='Run server on the given port.', type=int)
define('media_root', default='/mnt/diskstation/video',
    help='Directory where media folder is located.', type=str)


class BaseHandler(tornado.web.RequestHandler):
    """BaseHandler that all handlers inherit from."""
    pass


class BrowseHandler(BaseHandler):
    """Handler for browsing directories."""

    @tornado.web.asynchronous
    def get(self, path=''):
        dirpath = (os.path.join(options.media_root, path)
                if path else options.media_root)
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
        self.application.play(filepath)
        self.render(u'player.html', controls=self.application.control_names(),
                filename=ntpath.basename(filepath))


class ControlHandler(BaseHandler):
    """Handler to control the currently playing video."""

    @tornado.web.asynchronous
    def get(self, control):
        self.application.control(control)
        self.write(dict(message='Executed {}'.format(control)))
        self.finish()


class RaspberryPiPlayerApplication(tornado.web.Application):
    """App to play video on Raspberry Pi."""

    def __init__(self, handlers, **settings):
        self.__is_playing = False
        self.__player_process = None
        self.__control_map = {
            u'play': Control(u'p'),
            u'pause': Control(u'p'),
            u'volumn-up': Control(u'+'),
            u'volumn-down': Control(u'-'),
            u'seek+30': Control(u'\x1B[C'),
            u'seek-30': Control(u'\x1B[D'),
            u'seek+600': Control(u'\x1B[C'),
            u'seek-600': Control(u'\x1B[D'),
            u'quit': Control(u'q', post_processing=self.__quit),
        }
        tornado.web.Application.__init__(self, handlers, **settings)

    def control_names(self):
        """Get list of valid control names."""
        return self.__control_map.keys()

    def is_playing(self):
        return self.__is_playing

    def play(self, filepath):
        """Start video playback."""
        self.__quit()  # quit currently playback
        full_filepath = os.path.join(options.media_root, filepath)
        self.__player_process = psutil.Popen(
                [u'omxplayer', u'-r', u'-o', u'hdmi', full_filepath],
                stdin=subprocess.PIPE)
        subprocess.check_call(
                [u'echo', '.'],
                stdout=self.__player_process.stdin)
        self.__is_playing = True

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
    def __quit(self):
        """Do post playback cleanup."""
        if self.__player_process:
            process = self.__player_process
            for child in process.children(recursive=True):
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
    (r'/', tornado.web.RedirectHandler, {'url': '/browse'}),
    (r'/browse', BrowseHandler),
    (r'/browse/(.*)', BrowseHandler),
    (r'/play/(.*)', PlayerHandler),
    (r'/control/(.*)', ControlHandler),
], **settings)


def main():
    application.listen(options.port)
    ioloop = tornado.ioloop.IOLoop.instance()
    for (path, dirs, files) in os.walk(TEMPLATE_ROOT):
        for item in files:
            tornado.autoreload.watch(os.path.join(path, item))
    tornado.autoreload.start(ioloop)
    ioloop.start()


if __name__ == '__main__':
    main()
