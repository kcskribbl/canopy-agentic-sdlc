"""Render PNG evidence from the accepted service and its latest clean Maven verification."""
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont
import yaml

OUT = Path(__file__).resolve().parent
APP = OUT.parents[1] / "urlShortener"
FONT = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"


def font(size, bold=False, mono=False):
    family = ("consolab.ttf" if bold else "consola.ttf") if mono else ("segoeuib.ttf" if bold else "segoeui.ttf")
    try:
        return ImageFont.truetype(str(FONT / family),size)
    except OSError:
        return ImageFont.truetype("DejaVuSansMono.ttf" if mono else "DejaVuSans.ttf",size)


def panel(name,title,subtitle,rows,foot):
    im = Image.new("RGB",(1376,340+len(rows)*88),"#101c24")
    d = ImageDraw.Draw(im)
    d.rectangle((0,0,14,im.height),fill="#44d8aa")
    d.text((62,38),"CANOPY   /   ENGINEERING EVIDENCE",font=font(22,True,True),fill="#6de9c2")
    d.text((60,83),title,font=font(54,True),fill="#f3f6f5")
    d.text((63,160),subtitle,font=font(25),fill="#b1c6c8")
    for i,(tag,label,value) in enumerate(rows):
        y=229+88*i
        d.rounded_rectangle((56,y,1317,y+76),radius=10,fill="#1b303a")
        d.text((76,y+20),tag,font=font(25,True,True),fill="#73ebc7")
        d.text((237,y+19),label,font=font(26,True),fill="#fafafa")
        d.text((690,y+22),value,font=font(22,False,True),fill="#c9dbdf")
    d.text((63,im.height-58),foot,font=font(20),fill="#a9c1c1")
    im.save(OUT/name,optimize=True)


def call(port,method,path,body=None):
    conn=http.client.HTTPConnection("127.0.0.1",port,timeout=5)
    try:
        conn.request(method,path,json.dumps(body) if body else None,{"Content-Type":"application/json"})
        response=conn.getresponse()
        return response.status,response.getheader("Location"),response.read()
    finally:
        conn.close()


def main():
    jar=next((APP/"target").glob("links-*.jar"))
    suites=[ET.parse(p).getroot() for p in sorted((APP/"target/surefire-reports").glob("TEST-*.xml"))]
    assert suites and all(int(s.get("errors"))+int(s.get("failures"))==0 for s in suites)
    karate=json.loads((APP/"target/karate-reports/karate-summary-json.txt").read_bytes())
    with tempfile.TemporaryDirectory(prefix="canopy-image-") as directory:
        log=Path(directory,"startup.log")
        with log.open("wb") as stream:
            proc=subprocess.Popen(["java","-jar",str(jar),"--server.port=0","--server.address=127.0.0.1",
                                   "--spring.datasource.url=jdbc:h2:mem:imagecapture"],
                                  cwd=directory,stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
            try:
                for _ in range(160):
                    if proc.poll() is not None: raise RuntimeError("Service failed to start")
                    match=re.search(rb"Tomcat started on port (\d+)",log.read_bytes())
                    if match: break
                    time.sleep(.25)
                else: raise RuntimeError("Service readiness timeout")
                port=int(match[1])
                url="https://example.test/canopy"
                def stats():
                    status,_,raw=call(port,"GET","/api/stats")
                    assert status==200
                    return json.loads(raw)
                samples=[("Empty store",stats())]
                created,_,raw=call(port,"POST","/api/links",{"url":url})
                code=json.loads(raw)["code"]
                samples.append(("After creation",stats()))
                preview,_,raw=call(port,"GET","/api/links/"+code)
                assert json.loads(raw)=={"url":url}
                samples.append(("After preview",stats()))
                redirect,location,_=call(port,"GET","/r/"+code)
                unknown,_,_=call(port,"GET","/r/missing")
                samples.append(("After one redirect",stats()))
                assert (created,preview,redirect,unknown)==(201,200,302,404) and location==url
                assert [v["totalRedirects"] for _,v in samples]==[0,0,0,1]
            finally:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    panel("01-test-results.png","Local verification","Surefire test suites and Karate HTTP scenarios from the accepted application.",
          [("PASS",s.get("name").split(".")[-1],f"{s.get('tests')} tests  /  {s.get('failures')} failed  /  {s.get('skipped')} skipped") for s in suites]
          +[("KARATE","HTTP contract scenarios",f"{karate['scenariosPassed']} passed  /  {karate['scenariosfailed']} failed")],
          "Karate scenarios run inside PreviewContractTest; they are not added to the Maven test total.")
    panel("02-api-responses.png","Create, inspect, follow","Responses captured over loopback HTTP. Redirect following was disabled.",
          [(str(created),"POST /api/links","code: "+code),(str(preview),"GET /api/links/{code}","url: "+url),
           (str(redirect),"GET /r/{code}","Location: "+location),(str(unknown),"GET /r/missing","No matching link")],
          "Fresh in-memory H2 database. The example destination was never contacted.")
    panel("03-click-metrics.png","What counts as a visit?","Four successive GET /api/stats responses from the same isolated service.",
          [(f"0{i+1}",label,f"totalLinks: {v['totalLinks']}    totalRedirects: {v['totalRedirects']}") for i,(label,v) in enumerate(samples)],
          "Preview reads the saved destination. Only a successful redirect increments the counter.")
    contract=yaml.safe_load((APP/"openapi.yaml").read_bytes())
    panel("04-api-contract.png","API contract",f"{contract['info']['title']}   /   OpenAPI {contract['openapi']}   /   version {contract['info']['version']}",
          [(verb.upper(),path,"HTTP "+", ".join(map(str,op["responses"]))) for path,verbs in contract["paths"].items() for verb,op in verbs.items()],
          "Rendered from urlShortener/openapi.yaml. This is a contract view, not a hosted Swagger UI.")


if __name__=="__main__":
    main()
