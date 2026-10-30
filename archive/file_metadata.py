"""소유 파일에 딸린 macOS 메타데이터만 서명으로 확인한다."""
def owned_metadata(file,folder,allowed):
    if file.is_symlink() or not file.is_file():return False
    sibling=file.with_name(file.name[2:]).relative_to(folder).as_posix() if file.name.startswith('._') and len(file.name)>2 else None
    parent=file.parent.relative_to(folder).as_posix()
    if sibling not in allowed and not (file.name=='.DS_Store' and (parent=='.' or parent in allowed)):return False
    with file.open('rb') as stream:header=stream.read(8)
    return (sibling in allowed and header==b'\x00\x05\x16\x07\x00\x02\x00\x00') or (file.name=='.DS_Store' and header==b'\x00\x00\x00\x01Bud1')
