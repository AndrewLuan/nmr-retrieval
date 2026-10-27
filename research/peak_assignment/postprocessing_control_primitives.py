# 功能概述：H公开续行所需六个控制原语，来自冻结原supervisor的最小导入闭包。
# need核条件，sha/bound/read_bound核制品，save_new排他持久化，stamp记录UTC。
# 所有文件读写先调用已冻结runtime显式授权；不包含监督循环、模型或求解/评分。
import datetime,hashlib,json,os
from pathlib import Path
from portable_runtime import _config
def need(condition, message):
    if not condition:
        raise ValueError(message)

def sha(path):
    _config()
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()

def bound(item):
    _config()
    path = Path(item['path']).resolve()
    need(sha(path) == item['sha256'], 'bound_SHA:' + str(path))
    return path

def read_bound(path, expected):
    _config()
    need(sha(path) == expected, 'request_SHA')
    return json.loads(Path(path).read_text())

def save_new(path, value):
    _config()
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
