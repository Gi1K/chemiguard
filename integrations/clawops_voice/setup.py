"""Save phone settings through an SSH TTY; never place keys in shell history."""
import getpass
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import warnings

from dotenv import dotenv_values


TARGET = Path(__file__).resolve().parents[2] / '.env.clawops'


def save_settings(path: Path, original: str, updates: dict) -> None:
    if path.is_symlink() or path.read_text(encoding='utf-8') != original:
        raise ValueError('설정 파일이 변경됐습니다. 다시 실행해 주세요.')
    names = '|'.join(re.escape(name) for name in updates)
    pattern = re.compile(rf'^\s*(?:export\s+)?(?:{names})\s*=')
    lines = [line for line in original.splitlines() if not pattern.match(line)]
    for name, value in updates.items():
        escaped = value.replace('\\', '\\\\').replace("'", "\\'")
        lines.append(f"{name}='{escaped}'")
    fd, temporary = tempfile.mkstemp(prefix='.env.clawops-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            os.fchmod(output.fileno(), 0o600)
            output.write('\n'.join(lines) + '\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def phone_number(value: str) -> str:
    value = re.sub(r'[\s()-]', '', value)
    if value.startswith('+82'):
        value = '0' + value[3:]
    return value if re.fullmatch(r'0\d{8,10}', value) else ''


def prompt(label: str, previous: str, validate, hidden=False) -> str:
    suffix = ' [Enter: 기존 값 유지]' if previous else ''
    while True:
        reader = getpass.getpass if hidden else input
        value = reader(f'{label}{suffix}: ').strip() or previous
        result = validate(value)
        if result:
            return result
        print('빈 값 또는 잘못된 형식입니다. 다시 입력해 주세요.')


def main() -> int:
    if not sys.stdin.isatty():
        print('SSH 터미널에서 실행하세요. 원격 단일 명령에는 ssh -t가 필요합니다.')
        return 1
    if TARGET.is_symlink() or not TARGET.is_file():
        print('먼저 서버의 .env.clawops 설정 파일을 준비해야 합니다.')
        return 1
    original = TARGET.read_text(encoding='utf-8')
    config = dotenv_values(stream=io.StringIO(original), interpolate=False)
    if not config.get('CLAWOPS_ZONE_ID'):
        print('설정 파일의 CLAWOPS_ZONE_ID를 먼저 지정해 주세요.')
        return 1
    print('네 항목을 입력하면 수동 시연 전화가 활성화되고 자동 발신은 꺼집니다.')
    print('API 키는 붙여넣어도 화면에 표시되지 않습니다. 각 입력 후 Enter를 누르세요.')
    print('OpenAI 키 참조와 개소 설정은 유지합니다. 취소는 Ctrl+C입니다.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        api_key = prompt('1/4 ClawOps API 키', config.get('CLAWOPS_API_KEY') or '',
                         lambda v: v if re.fullmatch(r'[A-Za-z0-9._~+:/=-]+', v) else '', True)
    account_id = prompt('2/4 ClawOps Account ID', config.get('CLAWOPS_ACCOUNT_ID') or '',
                        lambda v: v if re.fullmatch(r'[A-Za-z0-9_-]+', v) else '')
    from_number = prompt('3/4 ClawOps에 등록한 발신번호', config.get('CLAWOPS_FROM_NUMBER') or '', phone_number)
    to_number = prompt('4/4 안전관리자 수신번호', config.get('CLAWOPS_TO_NUMBER') or '',
                       lambda v: phone_number(v) if phone_number(v) != from_number else '')
    save_settings(TARGET, original, {
        'CLAWOPS_API_KEY': api_key,
        'CLAWOPS_ACCOUNT_ID': account_id,
        'CLAWOPS_FROM_NUMBER': from_number,
        'CLAWOPS_TO_NUMBER': to_number,
        'CLAWOPS_ENABLED': 'true',
        'CLAWOPS_AUTO_CALL': 'false',
    })
    print('저장 완료. 아직 API 인증 확인·서비스 재시작·전화 발신은 하지 않았습니다.')
    print('영상 분석 종료 후 적용: systemctl --user restart chemiguard-monitor.service')
    print('이후 관제의 전화 알림 화면에서 시연 전화를 직접 시작할 수 있습니다.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print('\n취소했습니다. 입력한 값은 저장하지 않았습니다.')
        raise SystemExit(1)
    except getpass.GetPassWarning:
        print('숨김 입력이 불가능한 터미널입니다. SSH -t 연결을 확인하세요.')
        raise SystemExit(1)
    except ValueError as error:
        print(str(error))
        raise SystemExit(1)
    except OSError:
        print('설정 파일을 읽거나 저장하지 못했습니다. 파일 권한을 확인하세요.')
        raise SystemExit(1)
