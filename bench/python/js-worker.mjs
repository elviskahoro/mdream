// Warmed node worker for the mdream JS engine, used by bench/python-compare.py.
//
// Reads newline-delimited JSON requests {"html": "..."} on stdin and writes
// newline-delimited JSON responses {"markdown": "...", "elapsedMs": <number>}
// on stdout. The process stays alive across requests so node startup and
// module loading are excluded from measurement (the same warm-process
// treatment bench/cli-compare.sh gives non-JS runtimes); elapsedMs is measured
// with performance.now() around the htmlToMarkdown() call itself.
//
// Requires the built @mdream/js package: pnpm install && pnpm --filter @mdream/js build
import { performance } from 'node:perf_hooks'
import process from 'node:process'

let htmlToMarkdown = null
let buffer = ''

process.stdin.setEncoding('utf8')
// Pause until the engine import resolves so no request is dropped.
process.stdin.pause()

function handleLine(line) {
  let request
  try {
    request = JSON.parse(line)
  }
  catch {
    process.stderr.write('js-worker: skipping malformed request line\n')
    return
  }
  const start = performance.now()
  const markdown = htmlToMarkdown(request.html)
  const elapsedMs = performance.now() - start
  process.stdout.write(`${JSON.stringify({ markdown, elapsedMs })}\n`)
}

process.stdin.on('data', (chunk) => {
  buffer += chunk
  let newlineIndex = buffer.indexOf('\n')
  while (newlineIndex >= 0) {
    const line = buffer.slice(0, newlineIndex).trim()
    buffer = buffer.slice(newlineIndex + 1)
    newlineIndex = buffer.indexOf('\n')
    if (line && htmlToMarkdown) {
      handleLine(line)
    }
  }
})

process.stdin.on('end', () => process.exit(0))

async function loadEngine() {
  try {
    const module = await import('@mdream/js')
    htmlToMarkdown = module.htmlToMarkdown
    process.stdin.resume()
  }
  catch (error) {
    process.stderr.write(`@mdream/js not importable: ${error.message}\n`)
    process.exit(1)
  }
}

loadEngine()
