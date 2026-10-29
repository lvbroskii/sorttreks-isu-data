"""Check a source patch in a temporary tree. No network, site access or deployment."""
import json,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    site=Path(tmp)
    # A public minimal source bundle is sufficient to validate applyability without
    # publishing the entire Site or the local-only historical ISU captures.
    bundle=json.loads((root/'site-integration/base-files.json').read_text())
    for name,body in bundle.items():
        p=site/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body)
    subprocess.run(['git','init','-q',str(site)],check=True)
    subprocess.run(['git','-C',str(site),'apply','--check',str(root/'site-integration/changes.patch')],check=True)
    subprocess.run(['git','-C',str(site),'apply',str(root/'site-integration/changes.patch')],check=True)
    for name in ('calendar.mjs','isu-feed-contract.mjs','isu-feed-client.mjs','isu-feed-connect.mjs','programme-notice.mjs'):
        subprocess.run(['node','--check',str(site/'dist/assets'/name)],check=True)
    assert (site/'dist/assets/isu-feed-contract.mjs').read_text()==(root/'integration/feed.mjs').read_text()
    assert (site/'dist/assets/isu-feed-client.mjs').read_text()==(root/'integration/client.mjs').read_text().replace("'./feed.mjs'","'./isu-feed-contract.mjs'")
print('Site patch applies to pinned source; browser contract and client match repository source.')
