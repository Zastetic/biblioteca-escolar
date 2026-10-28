#!/usr/bin/env python3
"""Monitor do login da SED: avisa quando a SED começa/para de recusar as contas.

Por que existe: em 08/10/2026 a SED passou ~25 min devolvendo 403 "Usuário não pertence a rede
estadual!" para TODAS as contas, e o site parecia "senha errada". Este monitor mede de fora do site
e deixa registrado quando foi a SED e quando foi a credencial.

Uso (lê as credenciais que o autoava já guarda, nunca imprime senha):
    ./venv/bin/python tools/monitor_sed.py                 # uma medida
    ./venv/bin/python tools/monitor_sed.py --loop 300      # mede a cada 5 min
    ./venv/bin/python tools/monitor_sed.py --ra 555666777sp --ra 1098501007sp

Saída: uma linha por conta no stdout, e o histórico em tools/sed_monitor.log.
"""
import argparse
import datetime
import json
import os
import sys
import time

URL = "https://sedintegracoes.educacao.sp.gov.br/saladofuturobffapi/credenciais/api/LoginCompletoToken"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")
USERS_JSON = os.path.expanduser("~/automateava/Server/data/users.json")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sed_monitor.log")


def chave():
    chave = os.environ.get("SED_SUBSCRIPTION_KEY", "")
    if chave:
        return chave
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env):
        for linha in open(env, encoding="utf-8"):
            if linha.startswith("SED_SUBSCRIPTION_KEY="):
                return linha.split("=", 1)[1].strip()
    return ""


def medir(ra, senha, requests):
    headers = {"Accept": "application/json, text/plain, */*", "Content-Type": "application/json",
               "Ocp-Apim-Subscription-Key": chave(), "User-Agent": UA}
    try:
        resp = requests.post(URL, json={"user": ra, "senha": senha}, headers=headers, timeout=20)
    except Exception as e:
        return 0, f"rede: {type(e).__name__}"
    try:
        corpo = resp.json() or {}
    except ValueError:
        corpo = {}
    return resp.status_code, str(corpo.get("statusRetorno") or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ra", action="append", help="RA(s) a testar (padrão: os 2 primeiros do store)")
    ap.add_argument("--loop", type=int, metavar="SEG", help="repete a cada N segundos")
    ap.add_argument("--users-json", default=USERS_JSON, help="onde estão as credenciais guardadas")
    args = ap.parse_args()

    import requests

    store = {}
    if os.path.exists(args.users_json):
        store = json.load(open(args.users_json, encoding="utf-8"))
    alvos = args.ra or list(store.keys())[:2]
    if not alvos:
        print("Sem RA para testar (passe --ra ou tenha o users.json do autoava).")
        return 2

    anterior = None
    while True:
        agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        resultados = []
        for ra in alvos:
            senha = (store.get(ra) or {}).get("password")
            if not senha:
                resultados.append((ra, 0, "sem senha guardada"))
                continue
            resultados.append((ra,) + medir(ra, senha, requests))
        resumo = " | ".join(f"{ra}: {sc} {msg}" for ra, sc, msg in resultados)
        linha = f"[{agora}] {resumo}"
        print(linha, flush=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
        estado = tuples = tuple(sc for _, sc, _ in resultados)
        if anterior is not None and estado != anterior:
            print(f"    >>> MUDOU: {anterior} -> {estado}"
                  + ("   (SED voltou a aceitar)" if 200 in estado and 200 not in anterior else "")
                  + ("   (SED começou a recusar: é do lado da SED, não é senha)"
                     if 200 not in estado and 200 in anterior else ""), flush=True)
        anterior = estado
        if not args.loop:
            break
        time.sleep(args.loop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
