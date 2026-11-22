import { describe, expect, it } from 'vitest'
import { htmlToMarkdown, streamHtmlToMarkdown } from '../../src'
import { htmlToText } from '../../src/text'

const CASES: [string, string][] = [
  ['<p>a <a href="/x"></a> b</p>', 'a [](/x) b'],
  ['<a href="/x"><img src="a.png"></a><p>hi</p>', 'hi'],
  ['<a href="/y">t<img src="a.png"></a>', '[t](/y)'],
  ['<details><a href="/x"><img src="a.png"></a></details>', '<details></details>'],
  ['<details><a href="/x"><strong><img src="x"></strong></a></details>', '<details></details>'],
  ['<details><a href="/x"><sub><img src="x"></sub></a></details>', '<details></details>'],
  ['<details><a href="/x"><sub>text<img src="x"></sub></a></details>', '<details><a href="/x"><sub>text</sub></a></details>'],
  ['<details><a href="/x">t<img src="a.png"></a></details>', '<details><a href="/x">t</a></details>'],
]

describe('images: false', () => {
  it('preserves raw links with plugin or override output', async () => {
    const html = '<details><a href="/x"><span></span><img src="x"></a></details>'
    const expected = '<details><a href="/x">label</a></details>'
    for (const options of [
      { images: false, tagOverrides: { span: { enter: 'label' } } },
      { images: false, tagOverrides: { span: { exit: 'label' } } },
      { images: false, plugins: [{ onNodeEnter: (node: { name: string }) => node.name === 'span' ? 'label' : undefined }] },
      { images: false, plugins: [{ onNodeExit: (node: { name: string }) => node.name === 'span' ? 'label' : undefined }] },
    ]) {
      expect(htmlToMarkdown(html, options)).toBe(expected)
      for (let split = 1; split < html.length; split++) {
        const stream = new ReadableStream<string>({ start(controller) {
          controller.enqueue(html.slice(0, split))
          controller.enqueue(html.slice(split))
          controller.close()
        } })
        let output = ''
        for await (const part of streamHtmlToMarkdown(stream, options))
          output += part
        expect(output, `split at ${split}`).toBe(expected)
      }
    }
  })
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

  it('holds a raw anchor containing only wrapper markup until its image is dropped', async () => {
    const html = `<details><a href="/x">${'<sub></sub>'.repeat(1000)}<sub><img src="x"></sub></a></details>`
    const stream = new ReadableStream<string>({
      start(controller) {
        for (let i = 0; i < html.length; i += 100)
          controller.enqueue(html.slice(i, i + 100))
        controller.close()
      },
    })
    let output = ''
    for await (const part of streamHtmlToMarkdown(stream, { images: false }))
      output += part
    expect(output).toBe('<details></details>')
  })

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
