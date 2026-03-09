import os, glob

for f in glob.glob("ui/*.py"):
    with open(f, "rb") as fp:
        c = fp.read()
    try:
        t = c.decode("utf-8")
        print(f"{f} is valid utf-8")
        continue
    except UnicodeDecodeError:
        pass

    try:
        t = c.decode("utf-16le")
        with open(f, "w", encoding="utf-8") as op:
            op.write(t)
        print(f"Fixed {f} from utf-16le")
        continue
    except:
        pass

    try:
        t = c.decode("cp949")
        with open(f, "w", encoding="utf-8") as op:
            op.write(t)
        print(f"Fixed {f} from cp949")
    except:
        print(f"Failed to fix {f}")
