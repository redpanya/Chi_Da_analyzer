"""치(지직) 다(시보기) 분석기 실행기."""

import argparse
from pathlib import Path
import sys
import webbrowser
import os
import signal
import threading
import json

from archive import runtime


def main():
    runtime.configure()
    if len(sys.argv)==3 and sys.argv[1]=='--voice-candidate-worker':
        from workers.voice_candidates import main as candidate_main
        candidate_main(sys.argv[2]);return
    if len(sys.argv)==2 and sys.argv[1]=='--context-worker':
        from workers.context_server import main as context_main
        context_main();return
    if len(sys.argv) == 3 and sys.argv[1] == '--voice-worker':
        from workers.voices import main as voice_main
        voice_main(sys.argv[2])
        return
    if sys.platform not in ('darwin', 'win32'):
        raise SystemExit('macOS와 Windows에서 실행하세요')
    if sys.platform == 'win32':
        from archive.windows_runtime import protect_process_tree
        protect_process_tree()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=runtime.library_default())
    parser.add_argument('--no-open', action='store_true', help='브라우저 자동 열기 생략')
    parser.add_argument('--ready-file', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--parent-pid', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--stop-file', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--diagnose', action='store_true', help='포함 도구 실행 검사')
    args = parser.parse_args()
    if args.diagnose:
        print(json.dumps(runtime.diagnose(),ensure_ascii=False,indent=2));return
    from archive.jobs import Manager
    from archive.server import make_server
    manager = Manager(args.library)
    server, url = make_server(manager)
    def stop(*_): raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    stopping = threading.Event()
    if args.stop_file:
        def watch_stop():
            while not stopping.wait(.2):
                if args.stop_file.is_file():
                    server.shutdown(); return
        threading.Thread(target=watch_stop, daemon=True).start()
    if args.parent_pid:
        def watch_parent():
            while not stopping.wait(.5):
                if os.getppid() != args.parent_pid:
                    os.kill(os.getpid(),signal.SIGTERM);return
        threading.Thread(target=watch_parent,daemon=True).start()
    if args.ready_file:
        from archive.storage import save_json
        save_json(args.ready_file, {'url':url,'pid':os.getpid()})
    print(f'치(지직) 다(시보기) 분석기: {url}\n종료: Ctrl+C (진행 중 자료를 보존한 뒤 종료합니다)', flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('진행 중 작업을 정리하고 있습니다…', flush=True)
    finally:
        stopping.set()
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        server.server_close()
        manager.close()
        if args.ready_file: args.ready_file.unlink(missing_ok=True)


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
