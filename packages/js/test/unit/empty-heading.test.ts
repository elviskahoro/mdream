import { describe, expect, it } from 'vitest'
import { htmlToMarkdown, streamHtmlToMarkdown } from '../../src/index'

async function convertStream(html: string, chunkSize: number) {
  let offset = 0
  const input = new ReadableStream<string>({
    pull(controller) {
      if (offset < html.length) {
        controller.enqueue(html.slice(offset, offset + chunkSize))
        offset += chunkSize
      }
      else {
        controller.close()
      }
    },
  }, { highWaterMark: 0 })
  let output = ''
  for await (const chunk of streamHtmlToMarkdown(input))
    output += chunk
  return output
}

describe('empty headings', () => {
  const cases: [string, string][] = [
    ['<h1></h1><p>body</p>', 'body'],
    ['<p>a</p><h2> </h2><p>b</p>', 'a\n\nb'],
    ['<p>a</p><h2><span></span></h2><p>b</p>', 'a\n\nb'],
    ['<blockquote><h1></h1><p>x</p></blockquote>', '> x'],
    ['<ul><li><h1></h1><p>b</p></li></ul>', '- b'],
    ['<ol start="10"><li><h1></h1><p>b</p></li></ol>', '10. b'],
    ['<h1></h1>', ''],
    ['<h1><span><h2></h2></span></h1>', ''],
    ['<h1><span><h2></h2></span>outer</h1>', '#\n\nouter'],
    ['<h1>outer<span><h2></h2></span></h1>', '# outer'],
    ['<h1>T</h1><h2></h2><h3>U</h3>', '# T\n\n### U'],
  ]

  it('emits content before an unclosed heading ends', async () => {
    const input = new ReadableStream<string>({
      start(controller) {
        controller.enqueue(`<h1>${'<span>word</span>'.repeat(1000)}`)
      },
    })
    const iterator = streamHtmlToMarkdown(input)[Symbol.asyncIterator]()
    const first = await iterator.next()
    expect(first.value).toContain('# word')
    await iterator.return?.()
  })

  it.each(cases)('emits nothing for %s', (html, expected) => {
    expect(htmlToMarkdown(html)).toBe(expected)
  })

  it.each(cases)('streams to the same output for %s', async (html, expected) => {
    for (const size of [1, 2, 3, 5])
      expect(await convertStream(html, size)).toBe(expected)
  })
})
