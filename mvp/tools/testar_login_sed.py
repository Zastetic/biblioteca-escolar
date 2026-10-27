#!/usr/bin/env python3
"""
Diagnóstico do login da biblioteca: fala DIRETO com a SED (sem passar pelo site).

Serve para separar duas coisas que a tela do site não distingue:
  - o site está mandando o pedido errado?  (aqui você vê o pedido cru)
  - a SED está recusando as credenciais?   (aqui você vê a resposta crua)

Uso:
    cd ~/biblioteca_escolar/mvp
    ./venv/bin/python tools/testar_login_sed.py            # pergunta RA e senha (senha não aparece na tela)
    ./venv/bin/python tools/testar_login_sed.py --autoteste # testa a rede com credencial FALSA (não gasta tentativa sua)

A senha NUNCA é impressa, logada ou saída deste script — só usada no POST.
"""
import argparse
import getpass
import os
import sys
import unicodedata

SED_URL = "https://sedintegracoes.educacao.sp.gov.br/saladofuturobffapi/credenciais/api/LoginCompletoToken"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")


def chave_do_env():
    """Lê SED_SUBSCRIPTION_KEY do ambiente ou do mvp/.env (mesma fonte do run.sh)."""
    chave = os.environ.get("SED_SUBSCRIPTION_KEY", "")
    if chave:
        return chave
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        for linha in open(env_path, encoding="utf-8"):
            linha = linha.strip()
            if linha.startswith("SED_SUBSCRIPTION_KEY="):
                return linha.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def variantes(ra_bruto):
    """Formatos de RA que cada pessoa acaba digitando. O site usa o 2º (RA + 'sp')."""
    ra = ra_bruto.strip()
    numeros = "".join(c for c in ra if c.isdigit())
    if ra.lower().endswith("sp"):
        base = ra[:-2].strip()
    else:
        base = ra
    out = []

    def add(rotulo, valor):
        if valor and valor not in [v for _, v in out]:
            out.append((rotulo, valor))

    add("como você digitou (o site manda assim se já tiver 'sp')",
        ra if ra.lower().endswith("sp") else f"{ra}sp")
    add("RA + 'sp' minúsculo (é o que o site faz por padrão)", f"{base}sp")
    add("RA + 'SP' maiúsculo", f"{base.upper()}sp")
    add("RA só com os números + 'sp' (sem pontos/traços/espaços)", f"{numeros}sp")
    if numeros and len(numeros) < 13:
        add("RA preenchido com zeros à esquerda (13 dígitos) + 'sp'", f"{numeros.zfill(13)}sp")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--autoteste", action="store_true",
                    help="usa RA/senha falsos só para conferir se a rede e a chave respondem")
    args = ap.parse_args()

    try:
        import requests
    except ImportError:
        print("Falta a lib 'requests'. Rode com ./venv/bin/python (o venv do projeto tem).")
        return 2

    chave = chave_do_env()
    if not chave:
        print("SED_SUBSCRIPTION_KEY não encontrada (mvp/.env). Nada a testar.")
        return 2

    if args.autoteste:
        ra, senha = "0000000000", "credencial-falsa-autoteste"
        print("*** AUTOTESTE: credencial FALSA de propósito — esperado é 'Usuário ou senha incorretos!'\n")
    else:
        ra = input("RA (pode digitar com ou sem 'sp'; o site adiciona): ").strip()
        if not ra:
            print("RA vazio.")
            return 2
        senha = getpass.getpass("Senha da SED (não aparece na tela, não é gravada): ")
        if not senha:
            print("Senha vazia.")
            return 2
        print(f"\nRA digitado: {ra}   |   senha: {len(senha)} caractere(s)   (nada disso vai para log)")
        print("Aviso: cada tentativa conta como tentativa na SED. O script para no primeiro acerto.\n")

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": chave,
        "User-Agent": UA,
    }

    sucesso = False
    for rotulo, user in variantes(ra):
        try:
            r = requests.post(SED_URL, json={"user": user, "senha": senha}, headers=headers, timeout=20)
        except requests.RequestException as e:
            print(f"user={user!r:24} -> FALHA DE REDE: {type(e).__name__}: {e}")
            continue
        corpo = r.text[:300].replace("\n", " ")
        print(f"user={user!r:24} -> HTTP {r.status_code} | {corpo}")
        if r.status_code == 200 and '"token"' in r.text:
            dados = r.json().get("DadosUsuario", {})
            print("\n>>> DEU CERTO com este formato de RA:", repr(user))
            print("    nome:", dados.get("NAME"), "| cpf:", dados.get("NR_CPF"), "| email:", dados.get("EMAIL"))
            sucesso = True
            break

    print()
    if sucesso:
        print("CONCLUSÃO: a SED aceita suas credenciais; o problema estaria em como o SITE monta o RA")
        print("(hoje o site usa sempre '<RA>sp'). Anote o formato que deu certo e me avise.")
    else:
        if args.autoteste:
            print("CONCLUSÃO: rede + chave OK (a SED respondeu). Isso é o esperado no autoteste.")
        else:
            print("CONCLUSÃO: leia o CÓDIGO acima, não a mensagem:")
            print("  401 = credencial errada (RA/senha). O site mostra 'RA ou senha incorretos'.")
            print("  403 'Usuário não pertence a rede estadual!' = a SED ACEITOU a senha e recusou a conta.")
            print("       Isso já aconteceu com TODAS as contas de uma vez, em janelas da própria SED")
            print("       (medido 08/10/2026: 403 às 18:52 e 200 às 19:00 com a mesma credencial).")
            print("       Nesse caso não é senha nem RA: espere alguns minutos e tente de novo.")
            print("  429 = a SED está limitando acessos; espere alguns minutos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
