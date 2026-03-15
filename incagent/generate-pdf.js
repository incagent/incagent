const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

(async () => {
  const browser = await puppeteer.launch({
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();

  // Load the guide HTML (convert markdown to HTML first)
  const md = fs.readFileSync(path.join(__dirname, 'guide/how-to-build-an-ai-corporation.md'), 'utf8');

  // Simple markdown to HTML conversion for PDF
  const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body { font-family: Georgia, serif; font-size: 14px; line-height: 1.7; max-width: 680px; margin: 0 auto; padding: 40px; color: #1a1a1a; }
  h1 { font-size: 32px; margin-bottom: 8px; color: #0a0a0a; }
  h2 { font-size: 22px; margin-top: 48px; margin-bottom: 12px; border-bottom: 2px solid #f0c040; padding-bottom: 6px; }
  h3 { font-size: 17px; margin-top: 28px; margin-bottom: 8px; color: #333; }
  blockquote { border-left: 3px solid #f0c040; margin: 24px 0; padding: 12px 20px; background: #fafafa; font-style: italic; color: #444; }
  table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; }
  th { background: #f0c040; color: #000; padding: 8px 12px; text-align: left; }
  td { padding: 8px 12px; border-bottom: 1px solid #e0e0e0; }
  tr:nth-child(even) td { background: #f9f9f9; }
  code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 12px; font-family: monospace; }
  pre { background: #f0f0f0; padding: 16px; border-radius: 4px; overflow-x: auto; font-size: 12px; line-height: 1.5; }
  pre code { background: none; padding: 0; }
  hr { border: none; border-top: 1px solid #e0e0e0; margin: 40px 0; }
  .cover { text-align: center; padding: 80px 0 60px; border-bottom: 2px solid #f0c040; margin-bottom: 60px; }
  .cover h1 { font-size: 42px; }
  .cover .sub { font-size: 18px; color: #555; margin-top: 12px; }
  .cover .author { font-size: 14px; color: #888; margin-top: 32px; }
  a { color: #c09000; }
  p { margin-bottom: 14px; }
  li { margin-bottom: 6px; }
</style>
</head>
<body>
${mdToHtml(md)}
</body>
</html>`;

  function mdToHtml(text) {
    return text
      .replace(/^# (.*?)$/gm, '<h1>$1</h1>')
      .replace(/^## (.*?)$/gm, '<h2>$1</h2>')
      .replace(/^### (.*?)$/gm, '<h3>$1</h3>')
      .replace(/^> (.*?)$/gm, '<blockquote>$1</blockquote>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`(.*?)`/g, '<code>$1</code>')
      .replace(/```[\w]*\n([\s\S]*?)```/gm, '<pre><code>$1</code></pre>')
      .replace(/^\| (.*) \|$/gm, (match) => {
        const cells = match.split('|').filter(c => c.trim());
        return '<tr>' + cells.map(c => `<td>${c.trim()}</td>`).join('') + '</tr>';
      })
      .replace(/(<tr>.*<\/tr>\n)+/g, (m) => `<table>${m}</table>`)
      .replace(/^---$/gm, '<hr>')
      .replace(/^\d+\. (.*?)$/gm, '<li>$1</li>')
      .replace(/^- (.*?)$/gm, '<li>$1</li>')
      .replace(/(<li>.*<\/li>\n)+/g, (m) => `<ul>${m}</ul>`)
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
      .replace(/\n\n/g, '</p><p>')
      .replace(/^(?!<[hbptulio])/gm, '<p>')
      .replace(/<p><\/p>/g, '');
  }

  await page.setContent(html, { waitUntil: 'networkidle0' });

  await page.pdf({
    path: path.join(__dirname, 'guide/how-to-build-an-ai-corporation.pdf'),
    format: 'A4',
    margin: { top: '20mm', bottom: '20mm', left: '20mm', right: '20mm' },
    printBackground: true
  });

  await browser.close();
  console.log('PDF generated successfully.');
})();
