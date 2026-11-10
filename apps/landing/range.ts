// Byte-range responses for static media. Safari and iOS will not play a <video> unless the server answers
// `Range: bytes=…` with 206 Partial Content; hono's serveStatic always sends the whole file with 200.
// Returns null when the file is missing or the header is not a single bytes range, so the caller falls through.
export async function rangeResponse(path: string, header: string): Promise<Response | null> {
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (!m || (m[1] === '' && m[2] === '')) return null;
  const file = Bun.file(path);
  if (!(await file.exists())) return null;
  const size = file.size;
  let start: number;
  let end: number;
  if (m[1] === '') {
    start = Math.max(0, size - Number(m[2]));
    end = size - 1;
  } else {
    start = Number(m[1]);
    end = m[2] === '' ? size - 1 : Math.min(Number(m[2]), size - 1);
  }
  if (start >= size || start > end) {
    return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
  }
  return new Response(file.slice(start, end + 1), {
    status: 206,
    headers: {
      'Content-Type': file.type,
      'Content-Range': `bytes ${start}-${end}/${size}`,
      'Content-Length': String(end - start + 1),
      'Accept-Ranges': 'bytes',
    },
  });
}
