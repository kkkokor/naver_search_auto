import glob

for f in glob.glob("ui/tab_*.py"):
    with open(f, "rb") as fp:
        content = fp.read()
    
    try:
        # Try decoding as utf-16le (powershell default for Set-Content often)
        text = content.decode("utf-16le")
        if "api_client" in text:
            with open(f, "w", encoding="utf-8") as out:
                out.write(text)
            print("Fixed UTF-16:", f)
            continue
    except:
        pass

    try:
        # Try decoding as cp949 (Korean Windows ANSI)
        text = content.decode("cp949")
        if "api_client" in text:
            with open(f, "w", encoding="utf-8") as out:
                out.write(text)
            print("Fixed CP949:", f)
            continue
    except:
        pass
