import enum
import os.path
import tornado.ioloop
import tornado.web
import tornado.websocket
import uuid
import yt_dlp
from tornado.options import define, options, parse_command_line

define("port", default=8099, help="run on the given port", type=int)
define("debug", default=True, help="run in debug mode")


class DownloadStatus(str, enum.Enum):
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
        self.loop = tornado.ioloop.IOLoop.current()
        self.loop.run_in_executor(None, self.run)

    def progress_hook(self, status_dict):
        try:
            self.status = DownloadStatus(status_dict["status"])
        except ValueError:
            pass

        try:
            self.description = status_dict["filename"]
            self.progress = round(100. * status_dict["downloaded_bytes"] / status_dict["total_bytes"])
        except KeyError:
            pass

        self.notify()

    def run(self):
        try:
            self.status = DownloadStatus.started

            ydl_opts = {
                "no_color": True,
                "progress_hooks": [self.progress_hook]
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            self.status = DownloadStatus.finished

        except Exception as e:
            self.status = DownloadStatus.error
            self.description = str(e)
        finally:
            self.notify()

    def notify(self):
        for l in self.listeners:
            self.loop.add_callback(l.on_task_update, self)


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
