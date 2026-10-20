"""Narrow protected-base exceptions for reviewed complete source trees.

Not a general source or host allowlist. Exact trees and provenance must match;
all semantic review, unsafe mode, regression and protected merge gates remain.
"""
import json
import re
from urllib.parse import urlsplit
from git_change_records import read_path, _run_git

PATH = 'tools/config/reviewed-source-exceptions.json'
FIELDS = {'skill_id', 'kind', 'tree_oid', 'before_source', 'after_source', 'source_type', 'source_repo', 'evidence_url', 'verified_at'}

def load(repo, policy):
    raw = read_path(repo, policy, PATH)
    if raw is None:
        return []
    doc = json.loads(raw)
    if not isinstance(doc, dict) or doc.get('schema_version') != 1 or not isinstance(doc.get('entries'), list):
        raise ValueError('Invalid reviewed source exception ledger')
    seen = set()
    for e in doc['entries']:
        if not isinstance(e, dict) or set(e) != FIELDS:
            raise ValueError('Invalid source exception fields')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', e['skill_id']) or not re.fullmatch(r'[a-f0-9]{40}', e['tree_oid']):
            raise ValueError('Invalid source exception identity')
        key = (e['skill_id'], e['tree_oid'])
        if key in seen:
            raise ValueError('Duplicate source exception')
        seen.add(key)
        for field in ('after_source', 'evidence_url'):
            url = urlsplit(e[field])
            if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
                raise ValueError('Source exceptions require explicit HTTPS evidence')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', e['verified_at']) or e['source_type'] not in ('official', 'community'):
            raise ValueError('Invalid source exception metadata')
        if e['kind'] == 'hosted-source':
            if e['before_source'] is not None or e['source_repo'] is not None:
                raise ValueError('Hosted source exception is only for a reviewed addition without repository')
        elif e['kind'] == 'source-repin':
            prefix = 'https://github.com/' + str(e['source_repo']) + '/tree/'
            pattern = re.escape(prefix) + r'[a-f0-9]{40}/[^?#]+'
            if not all(isinstance(e[f], str) and re.fullmatch(pattern, e[f]) for f in ('before_source', 'after_source')):
                raise ValueError('Repin must bind immutable commits in the same repository')
            if e['before_source'].split('/')[7:] != e['after_source'].split('/')[7:] or e['before_source'] == e['after_source']:
                raise ValueError('Repin cannot change upstream subtree')
        else:
            raise ValueError('Unsupported source exception kind')
    return doc['entries']

def apply(repo, head, skill_id, change_type, before, after, blockers, entries, readme):
    if after is None:
        return blockers, []
    provenance = after['provenance']
    for e in entries:
        if e['skill_id'] != skill_id:
            continue
        if any(provenance.get(f) != (e[k].lower() if f == 'source_repo' and isinstance(e[k], str) else e[k]) for f, k in [('source','after_source'),('source_type','source_type'),('source_repo','source_repo')]):
            continue
        if (before or {}).get('provenance', {}).get('source') != e['before_source']:
            continue
        tree = _run_git(repo, ['rev-parse', '--verify', f'{head}:skills/{skill_id}']).decode().strip()
        if tree != e['tree_oid']:
            continue
        if e['kind'] == 'hosted-source' and change_type == 'added' and e['evidence_url'] in readme:
            reason = f'{skill_id}:new_external_skill_invalid_source_repo'
        elif e['kind'] == 'source-repin' and change_type == 'modified':
            reason = f'{skill_id}:provenance_identity_changed:source'
        else:
            continue
        if reason in blockers:
            return [b for b in blockers if b != reason], [f"{skill_id}:{e['kind']}:{tree}"]
    return blockers, []
