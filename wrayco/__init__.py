import asyncio
import enum
import os.path
import re
import tornado.ioloop
import tornado.web
import tornado.websocket
import uuid
from tornado.options import define, options, parse_command_line

define("port", default=8099, help="run on the given port", type=int)
define("debug", default=True, help="run in debug mode")


class DownloadStatus:
    started = "started"
    error = "error"
    idle = "idle"
    finished = "finished"


class DownloadTask:
    def __init__(self, url):
        self.url = url
        self.progress = 0
        self.description = url
        self.id = str(uuid.uuid4())
        self.listeners = []
        self.status = DownloadStatus.idle

    def start(self):
        self.task = asyncio.get_event_loop().create_task(self.run())

    async def run(self):
        try:
            self.status = DownloadStatus.started

            proc = await asyncio.create_subprocess_exec(
                "youtube-dl",
                "--newline",
                self.url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)

            while True:
                line = await proc.stdout.readline()
                if line == b'':
                    break
                line = line.decode("ASCII")

                m = re.match("^\[download\] Destination: (.*)", line)
                if m:
                    self.description = m.group(1)
                    self.notify()

                m = re.match("^\[download\]\s+(.*)% of ", line)
                if m:
                    self.progress = float(m.group(1))
                    self.notify()

                m = re.match('^\[ffmpeg\] Merging formats into "(.*)"', line)
                if m:
                    self.description = m.group(1)
                    self.notify()
            
            await proc.wait()
            if proc.returncode == 0:
                self.progress = 100
                self.status = DownloadStatus.finished
            else:
                error = await proc.stderr.read()
                error = error.decode("UTF-8")
                self.status = DownloadStatus.error
                raise RuntimeError(error)
        except Exception as e:
            self.status = DownloadStatus.error
            self.description = str(e)
        finally:
            self.notify()

    def notify(self):
        for l in self.listeners:
            l.on_task_update(self)


class TaskWebSocket(tornado.websocket.WebSocketHandler):
    def open(self):
        downloader.listeners.append(self)

    def on_task_update(self, task):
        self.write_message({
            "id": task.id,
            "description": task.description,
            "progress": task.progress,
            "status": task.status
        })

    def on_close(self):
        downloader.listeners.remove(self)


class Downloader:
    def __init__(self):
        self.tasks = []
        self.listeners = []

    def start_download(self, url):
        task = DownloadTask(url)
        task.listeners.append(self)
        self.tasks.append(task)
        task.start()

    def on_task_update(self, task):
        for l in self.listeners:
            l.on_task_update(task)
        

downloader = Downloader()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html", tasks=downloader.tasks)

    def post(self):
        url = self.get_argument("url")
        downloader.start_download(url)
        return self.get()


def main():
    parse_command_line()
    app = tornado.web.Application(
        [
            (r"/", MainHandler),
            (r"/ws", TaskWebSocket)
        ],
        cookie_secret=str(uuid.uuid4()),
        template_path=os.path.join(os.path.dirname(__file__), "templates"),
        static_path=os.path.join(os.path.dirname(__file__), "static"),
        xsrf_cookies=True,
        debug=options.debug,
    )
    app.listen(options.port)
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()
