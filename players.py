"""Independent model routing for each seat. Credentials stay in environment variables."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request


class PlayerError(Exception):
    """A model request failed without changing the game."""


def player_config(seat_index):
    config = {
        'provider': 'openai' if os.getenv('WOLF_MODEL') else 'codex',
        'model': os.getenv('WOLF_MODEL', ''),
        'base_url': os.getenv('WOLF_BASE_URL', 'https://api.openai.com/v1'),
        'api_key_env': 'WOLF_API_KEY',
        'timeout': 120,
    }
    filename = os.getenv('WOLF_PLAYERS_FILE')
    if filename:
        try:
            data = json.loads(Path(filename).read_text(encoding='utf-8'))
            config.update(data.get('default', {}))
            config.update(data.get('seats', {}).get(str(seat_index + 1), {}))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise PlayerError('玩家模型配置文件无效，请检查 WOLF_PLAYERS_FILE') from exc
    if config['provider'] not in ('codex', 'openai'):
        raise PlayerError('玩家 provider 仅支持 codex 或 openai')
    for key in ('model', 'base_url', 'api_key_env'):
        if not isinstance(config.get(key), str):
            raise PlayerError('玩家模型配置字段类型错误')
    if not isinstance(config['timeout'], (int, float)) or not 1 <= config['timeout'] <= 600:
        raise PlayerError('玩家模型 timeout 必须在 1 至 600 秒之间')
    return config


def public_player(seat_index):
    config = player_config(seat_index)
    return {
        'provider': config['provider'],
        'model': config['model'] or 'Codex 默认模型',
        'label': 'Codex' if config['provider'] == 'codex' else config['model'],
    }


def _parse_reply(raw):
    try:
        start = raw.index('{')
        value = json.loads(raw[start:raw.rindex('}') + 1])
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError) as exc:
        raise PlayerError('模型回复格式无效，请重试本次行动') from exc


def _http_request(config, messages, max_tokens):
    if not config['model']:
        raise PlayerError('请设置此座位的模型名称')
    body = json.dumps(dict(model=config['model'], messages=messages, max_tokens=max_tokens)).encode()
    headers = {'Content-Type': 'application/json'}
    key = os.getenv(config['api_key_env'])
    if key:
        headers['Authorization'] = 'Bearer ' + key
    url = config['base_url'].rstrip('/') + '/chat/completions'
    request = urllib.request.Request(url, body, headers)
    try:
        with urllib.request.urlopen(request, timeout=config['timeout']) as response:
            result = json.load(response)
        return _parse_reply(result['choices'][0]['message']['content'])
    except urllib.error.HTTPError as exc:
        raise PlayerError(f'模型服务返回 HTTP {exc.code}，请检查模型配置后重试') from exc
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise PlayerError('模型服务连接失败或回复无效，请重试') from exc


def _codex_request(config, messages):
    executable = shutil.which('codex')
    if not executable:
        raise PlayerError('未找到 Codex，请安装并登录，或配置 OpenAI 兼容接口')
    # Each invocation gets only this player's visible messages and an empty working directory.
    with tempfile.TemporaryDirectory(prefix='wolf-player-') as folder:
        result_file = Path(folder) / 'reply.json'
        command = [executable, 'exec', '--ignore-user-config', '--ephemeral',
                   '--skip-git-repo-check', '--sandbox', 'read-only', '-C', folder,
                   '--color', 'never', '-o', str(result_file)]
        for feature in ('shell_tool', 'apps', 'multi_agent', 'browser_use', 'computer_use',
                        'image_generation', 'view_image', 'plugins', 'skill_search', 'goals'):
            command.extend(['-c', f'features.{feature}=false'])
        command.extend(['-c', 'web_search="disabled"', '-c', 'project_doc_max_bytes=0',
                        '-c', 'approval_policy="never"'])
        if config['model']:
            command.extend(['--model', config['model']])
        command.append('-')
        prompt = ('你正在扮演狼人杀玩家。只根据以下消息生成游戏回复。'
                  '不使用工具、不读取文件。严格只输出要求的 JSON 对象。\n'
                  + json.dumps(messages, ensure_ascii=False))
        try:
            completed = subprocess.run(command, input=prompt, text=True, capture_output=True,
                                       timeout=config['timeout'], cwd=folder)
            if completed.returncode != 0 or not result_file.exists():
                raise PlayerError('Codex 调用失败，请检查本机登录和网络后重试')
            return _parse_reply(result_file.read_text(encoding='utf-8'))
        except subprocess.TimeoutExpired as exc:
            raise PlayerError('Codex 回复超时，请重试本次行动') from exc
        except OSError as exc:
            raise PlayerError('无法启动 Codex，请检查本机安装') from exc


def request_player(seat_index, messages, *, max_tokens=1600):
    config = player_config(seat_index)
    if config['provider'] == 'codex':
        return _codex_request(config, messages)
    return _http_request(config, messages, max_tokens)
