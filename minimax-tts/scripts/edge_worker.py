"""Key-free online Edge TTS worker; narration arrives on stdin, never argv."""
import asyncio,json,sys
from pathlib import Path
import edge_tts

async def generate(spec):
    rate=f"{round((spec['speed']-1)*100):+d}%"
    communicate=edge_tts.Communicate(spec['text'],spec['voice'],rate=rate)
    await communicate.save(spec['output'])
    if Path(spec['output']).stat().st_size<1024:
        raise RuntimeError('empty_edge_audio')

if __name__=='__main__':
    try:asyncio.run(generate(json.load(sys.stdin)))
    except Exception as exc:
        print(type(exc).__name__,file=sys.stderr);sys.exit(1)
