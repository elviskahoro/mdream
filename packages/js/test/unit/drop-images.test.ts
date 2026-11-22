import { describe, expect, it } from 'vitest'
import { htmlToMarkdown, streamHtmlToMarkdown } from '../../src'
import { htmlToText } from '../../src/text'

const CASES: [string, string][] = [
  ['<p>a <a href="/x"></a> b</p>', 'a [](/x) b'],
  ['<a href="/x"><img src="a.png"></a><p>hi</p>', 'hi'],
  ['<a href="/y">t<img src="a.png"></a>', '[t](/y)'],
  ['<details><a href="/x"><img src="a.png"></a></details>', '<details></details>'],
  ['<details><a href="/x"><strong><img src="x"></strong></a></details>', '<details></details>'],
  ['<details><a href="/x">t<img src="a.png"></a></details>', '<details><a href="/x">t</a></details>'],
]

describe('images: false', () => {
  for (const [html, expected] of CASES) {
    it(`converts ${html}`, async () => {
      expect(htmlToMarkdown(html, { images: false })).toBe(expected)
      for (let split = 1; split < html.length; split++) {
        let out = ''
        const chunks = [html.slice(0, split), html.slice(split)]
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            for (const chunk of chunks)
              controller.enqueue(new TextEncoder().encode(chunk))
            controller.close()
          },
        })
        for await (const part of streamHtmlToMarkdown(stream, { images: false }))
          out += part
        expect(out, `split at ${split}`).toBe(expected)
      }
    })
  }

  it('streams a long raw HTML anchor before it closes', async () => {
    const prefix = `<details><a href="/x">${'visible text '.repeat(1000)}`
    let controller!: ReadableStreamDefaultController<string>
    const input = new ReadableStream<string>({ start(value) { controller = value } })
    const iterator = streamHtmlToMarkdown(input, { images: false })[Symbol.asyncIterator]()
    controller.enqueue(prefix)
    const first = await iterator.next()
    controller.enqueue('more text <img src="x">')
    const second = await iterator.next()
    expect((first.value || '') + (second.value || '')).toContain('<a href="/x">')
    expect(second.value!.length).toBeGreaterThan(1000)
    controller.close()
    let result = (first.value || '') + (second.value || '')
    for await (const part of { [Symbol.asyncIterator]: () => iterator })
      result += part
    expect(result).toBe(htmlToMarkdown(`${prefix}more text <img src="x">`, { images: false }))
  })

  it('suppresses image plugin output on enter and exit', () => {
    for (const hook of ['onNodeEnter', 'onNodeExit'] as const) {
      const plugins = [{ [hook]: (node: { name: string }) => node.name === 'img' ? 'IMG' : undefined }]
      const options = { images: false, plugins }
      expect(htmlToMarkdown('<p>a<img src="b.png">b</p>', options)).toBe('ab')
      expect(htmlToText('<p>a<img src="b.png">b</p>', options)).toBe('ab')
    }
  })

  it('suppresses an image override', () => {
    const tagOverrides = { img: { enter: 'IMG' } }
    expect(htmlToMarkdown('<p>a <img src="b.png"> c</p>', { images: false, tagOverrides })).toBe('a c')
    expect(htmlToText('<p>a <img src="b.png"> c</p>', { images: false, tagOverrides })).toBe('a c')
  })
})
