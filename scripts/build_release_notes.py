"""Build public release notes from .github/releases.json; --check detects stale outputs."""
from __future__ import annotations
import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def outputs():
    releases = json.loads((ROOT / '.github/releases.json').read_text())['releases']
    versions = [r['version'] for r in releases]
    assert versions and len(versions) == len(set(versions)), 'Release versions must be unique'
    assert all(re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9.]+)?', v) for v in versions)
    md = ['# Changelog', '', 'Release notes for Sonvane. Versions describe shipped application changes, not new versions of the underlying models.', '', 'Generated from [release records](../.github/releases.json). The newest release appears first.', '']
    cards = []
    for release in releases:
        v, date = release['version'], release['date']
        md += [f"## {v} — {date}", '', f"**{release['title']}**", '', release['summary'], '']
        groups = []
        for title, items in release['changes'].items():
            md += [f'### {title}', ''] + [f'- {item}' for item in items] + ['']
            groups.append(f'<section><h3>{html.escape(title)}</h3><ul>' + ''.join(f'<li>{html.escape(item)}</li>' for item in items) + '</ul></section>')
        cards.append(f'<article id="v{v}"><div class="release-meta"><span>v{v}</span><time datetime="{date}">{date}</time></div><h2>{html.escape(release["title"])}</h2><p>{html.escape(release["summary"])}</p><div class="changes">' + ''.join(groups) + '</div></article>')
    page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sonvane — Updates</title><link rel="icon" href="/assets/sonvane.svg"><link rel="stylesheet" href="/updates/updates.css"></head>
<body><header><a class="brand" href="/demo/"><img src="/assets/sonvane.svg" width="28" height="28" alt="">sonvane<span>.</span></a><nav aria-label="Product navigation"><a href="/demo/">Overview</a><a href="/studio/">Studio</a></nav></header>
<main><div class="intro"><p>SONVANE / RELEASE NOTES</p><h1>What's new</h1><p>What changed, when it shipped, and what to expect.</p></div>''' + ''.join(cards) + '''</main><footer><a href="https://github.com/yonghyunk1m/sonvane/blob/main/docs/CHANGELOG.md">Changelog on GitHub ↗</a></footer></body></html>\n'''
    result = {ROOT / 'VERSION': versions[0] + '\n', ROOT / 'deploy/huggingface/VERSION': versions[0] + '\n', ROOT / 'docs/CHANGELOG.md': '\n'.join(md), ROOT / 'app/static/updates/index.html': page}
    badge = f'<!-- release:start --><a class="release-link" href="/updates/" aria-label="Sonvane version {versions[0]}, view updates">v{versions[0]} · What’s new</a><!-- release:end -->'
    for relative in ['app/static/demo/index.html', 'app/static/studio/index.html']:
        path = ROOT / relative
        text = path.read_text()
        if '<!-- release:start -->' in text:
            text = re.sub(r'<!-- release:start -->.*?<!-- release:end -->', badge, text, flags=re.S)
        else:
            text = text.replace('</footer>', badge + '</footer>')
        result[path] = text
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    stale = []
    for path, text in outputs().items():
        if not path.exists() or path.read_text() != text:
            stale.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
    if args.check and stale:
        raise SystemExit('Stale release outputs: ' + ', '.join(stale))
    print('Release outputs are current.' if args.check else 'Built release notes and page version links.')

if __name__ == '__main__':
    main()
