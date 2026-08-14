# -*- coding: utf-8 -*-
import os
import sys
import json
import shutil
import zipfile
import hashlib
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

UPDATE_FORMAT = "SRSTUDIO_UPDATE_1"
PRODUCT = "SR Studio"


def _sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(value):
    p=Path(str(value).replace("\\","/"))
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise RuntimeError(f"Caminho inválido no pacote: {value}")
    if p.parts[0].lower() in {"dados","__pycache__"}:
        raise RuntimeError(f"O pacote tentou alterar dados do usuário: {value}")
    if p.suffix.lower() in {".db",".sqlite",".sqlite3"}:
        raise RuntimeError(f"O pacote tentou substituir um banco de dados: {value}")
    return p


def _version_tuple(v):
    parts=[]
    for x in str(v).strip().split("."):
        try: parts.append(int(x))
        except Exception: parts.append(0)
    return tuple((parts+[0,0,0])[:4])


def inspect_update(package, current_version):
    package=Path(package)
    if not package.exists(): raise RuntimeError("Arquivo de atualização não encontrado.")
    with zipfile.ZipFile(package,"r") as z:
        try: manifest=json.loads(z.read("manifest.json").decode("utf-8-sig"))
        except Exception as e: raise RuntimeError("Pacote inválido: manifest.json ausente ou corrompido.") from e
        if manifest.get("format")!=UPDATE_FORMAT or manifest.get("product")!=PRODUCT:
            raise RuntimeError("Este arquivo não é uma atualização válida do SR Studio.")
        target=str(manifest.get("to_version","")).strip()
        if not target: raise RuntimeError("A atualização não informa a versão de destino.")
        min_ver=str(manifest.get("min_version","")).strip()
        max_ver=str(manifest.get("max_version","")).strip()
        cur=_version_tuple(current_version)
        if min_ver and cur < _version_tuple(min_ver):
            raise RuntimeError(f"Esta atualização exige SR Studio {min_ver} ou superior.")
        if max_ver and cur > _version_tuple(max_ver):
            raise RuntimeError(f"Esta atualização foi feita para versões até {max_ver}.")
        files=manifest.get("files",[])
        if not isinstance(files,list) or not files: raise RuntimeError("O pacote não possui arquivos de atualização.")
        for item in files:
            rel=_safe_rel(item.get("path",""))
            member="payload/"+rel.as_posix()
            if member not in z.namelist(): raise RuntimeError(f"Arquivo ausente no pacote: {rel}")
            expected=str(item.get("sha256","")).lower().strip()
            if not expected: raise RuntimeError(f"Hash ausente para: {rel}")
            data=z.read(member)
            got=hashlib.sha256(data).hexdigest()
            if got!=expected: raise RuntimeError(f"Falha de integridade em: {rel}")
        for value in manifest.get("delete",[]): _safe_rel(value)
        return manifest


def apply_update(package, app_dir, current_version, history_file=None):
    package=Path(package); app_dir=Path(app_dir)
    manifest=inspect_update(package,current_version)
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    update_root=app_dir/"atualizacoes"
    backup=update_root/"backups"/stamp
    backup.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="srstudio_update_") as td:
        td=Path(td)
        with zipfile.ZipFile(package,"r") as z:
            for item in manifest["files"]:
                rel=_safe_rel(item["path"])
                member="payload/"+rel.as_posix()
                src=td/rel; src.parent.mkdir(parents=True,exist_ok=True)
                src.write_bytes(z.read(member))
            # Backup + replace.
            for item in manifest["files"]:
                rel=_safe_rel(item["path"]); dst=app_dir/rel; src=td/rel
                if dst.exists():
                    b=backup/rel; b.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(dst,b)
                dst.parent.mkdir(parents=True,exist_ok=True)
                tmp=dst.with_name(dst.name+".srupdate_tmp")
                shutil.copy2(src,tmp)
                os.replace(tmp,dst)
            for value in manifest.get("delete",[]):
                rel=_safe_rel(value); dst=app_dir/rel
                if dst.exists():
                    b=backup/rel; b.parent.mkdir(parents=True,exist_ok=True)
                    if dst.is_file(): shutil.copy2(dst,b); dst.unlink()
                    elif dst.is_dir(): shutil.copytree(dst,b,dirs_exist_ok=True); shutil.rmtree(dst)
    if history_file:
        history_file=Path(history_file)
        try:
            hist=json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else []
            if not isinstance(hist,list): hist=[]
        except Exception: hist=[]
        hist.append({"date":datetime.now().isoformat(timespec="seconds"),"from":current_version,"to":manifest.get("to_version"),"file":package.name,"backup":str(backup)})
        history_file.parent.mkdir(parents=True,exist_ok=True)
        history_file.write_text(json.dumps(hist[-50:],ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest,backup


def build_update(package_path, source_root, files, from_version, to_version, notes="", min_version=None, max_version=None):
    """Utilitário incluído para montar pacotes .srupdate de forma reproduzível."""
    package_path=Path(package_path); source_root=Path(source_root)
    manifest={"format":UPDATE_FORMAT,"product":PRODUCT,"from_version":from_version,"to_version":to_version,
              "min_version":min_version or from_version,"max_version":max_version or from_version,
              "notes":notes,"created_at":datetime.now().isoformat(timespec="seconds"),"files":[],"delete":[]}
    package_path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(package_path,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for value in files:
            rel=_safe_rel(value); src=source_root/rel
            if not src.exists() or not src.is_file(): raise RuntimeError(f"Arquivo não encontrado: {rel}")
            digest=_sha256(src)
            manifest["files"].append({"path":rel.as_posix(),"sha256":digest,"size":src.stat().st_size})
            z.write(src,"payload/"+rel.as_posix())
        z.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2))
    return manifest
