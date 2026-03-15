const PDFDocument = require('pdfkit');
const fs = require('fs');
const path = require('path');

const md = fs.readFileSync(path.join(__dirname, 'guide/how-to-build-an-ai-corporation.md'), 'utf8');
const lines = md.split('\n');

const doc = new PDFDocument({
  size: 'A4',
  margins: { top: 60, bottom: 60, left: 72, right: 72 },
  info: {
    Title: 'How to Build an AI Corporation',
    Author: 'Incagent DAO LLC',
    Subject: 'AI-native business formation and operations',
  }
});

const out = fs.createWriteStream(path.join(__dirname, 'guide/how-to-build-an-ai-corporation.pdf'));
doc.pipe(out);

const ACCENT = '#c09000';
const TEXT = '#1a1a1a';
const MUTED = '#555555';
const W = 451; // usable width (595 - 72 - 72)

let inCodeBlock = false;
let codeBuffer = [];
let tableBuffer = [];
let inTable = false;
let listBuffer = [];
let inList = false;

function flushList() {
  if (listBuffer.length === 0) return;
  listBuffer.forEach(item => {
    doc.fillColor(ACCENT).text('•', { continued: true, width: 16 });
    doc.fillColor(TEXT).text('  ' + item, { width: W - 20 });
  });
  listBuffer = [];
  inList = false;
  doc.moveDown(0.4);
}

function flushTable() {
  if (tableBuffer.length === 0) return;
  // skip separator rows
  const rows = tableBuffer.filter(r => !r.match(/^[\|\s\-:]+$/));
  const colW = W / 3;
  rows.forEach((row, i) => {
    const cells = row.split('|').filter(c => c.trim()).map(c => c.trim());
    if (i === 0) {
      doc.fillColor('#000000').rect(doc.x, doc.y, W, 18).fill(ACCENT);
      cells.forEach((cell, j) => {
        doc.fillColor('#000000').text(cell, doc.page.margins.left + j * colW, doc.y - 16, { width: colW - 8, lineBreak: false });
      });
      doc.moveDown(0.2);
    } else {
      if (i % 2 === 0) doc.fillColor('#f5f5f5').rect(doc.x, doc.y, W, 16).fill('#f5f5f5');
      cells.forEach((cell, j) => {
        doc.fillColor(TEXT).text(cell, doc.page.margins.left + j * colW, doc.y, { width: colW - 8, lineBreak: false });
      });
      doc.moveDown(0.2);
    }
  });
  tableBuffer = [];
  inTable = false;
  doc.moveDown(0.6);
}

function renderLine(line) {
  // Code block
  if (line.startsWith('```')) {
    if (!inCodeBlock) {
      inCodeBlock = true;
      codeBuffer = [];
    } else {
      inCodeBlock = false;
      const code = codeBuffer.join('\n');
      doc.fillColor('#f0f0f0').roundedRect(doc.x, doc.y, W, codeBuffer.length * 14 + 16, 4).fill('#f0f0f0');
      doc.fillColor(MUTED).font('Courier').fontSize(10).text(code, doc.x + 8, doc.y - codeBuffer.length * 14 - 8, { width: W - 16 });
      doc.font('Helvetica').fontSize(11);
      doc.moveDown(0.8);
    }
    return;
  }
  if (inCodeBlock) { codeBuffer.push(line); return; }

  // Table
  if (line.startsWith('|')) {
    inTable = true;
    tableBuffer.push(line);
    return;
  }
  if (inTable && !line.startsWith('|')) {
    flushTable();
  }

  // HR
  if (line.match(/^---+$/)) {
    flushList();
    doc.moveDown(0.5);
    doc.strokeColor('#e0e0e0').lineWidth(1).moveTo(doc.x, doc.y).lineTo(doc.x + W, doc.y).stroke();
    doc.moveDown(0.5);
    return;
  }

  // Headings
  if (line.startsWith('# ')) {
    flushList();
    const text = line.replace(/^# /, '').replace(/\*\*(.*?)\*\*/g, '$1');
    doc.addPage();
    doc.fillColor(ACCENT).fontSize(28).font('Helvetica-Bold').text('⚡ ' + text, { align: 'left' });
    doc.fillColor('#e0e0e0').moveDown(0.2).rect(doc.x, doc.y, W, 2).fill('#e0e0e0');
    doc.moveDown(0.8);
    doc.fillColor(TEXT).font('Helvetica').fontSize(11);
    return;
  }
  if (line.startsWith('## ')) {
    flushList();
    const text = line.replace(/^## /, '');
    doc.moveDown(0.6);
    doc.fillColor(ACCENT).fontSize(16).font('Helvetica-Bold').text(text);
    doc.fillColor('#e0c060').rect(doc.x, doc.y, W, 1.5).fill('#e0c060');
    doc.moveDown(0.5);
    doc.fillColor(TEXT).font('Helvetica').fontSize(11);
    return;
  }
  if (line.startsWith('### ')) {
    flushList();
    const text = line.replace(/^### /, '');
    doc.moveDown(0.4);
    doc.fillColor('#333333').fontSize(13).font('Helvetica-Bold').text(text);
    doc.moveDown(0.3);
    doc.fillColor(TEXT).font('Helvetica').fontSize(11);
    return;
  }

  // Blockquote
  if (line.startsWith('> ')) {
    flushList();
    const text = line.replace(/^> /, '');
    doc.fillColor('#f8f8f0').rect(doc.x, doc.y, W, 36).fill('#f8f8f0');
    doc.fillColor(ACCENT).rect(doc.x, doc.y - 36, 3, 36).fill(ACCENT);
    doc.fillColor(MUTED).font('Helvetica-Oblique').fontSize(12).text(text, doc.x + 12, doc.y - 30, { width: W - 16 });
    doc.font('Helvetica').fontSize(11);
    doc.moveDown(0.8);
    return;
  }

  // List items
  if (line.match(/^[-*] /) || line.match(/^\d+\. /)) {
    inList = true;
    const text = line.replace(/^[-*] /, '').replace(/^\d+\. /, '').replace(/\*\*(.*?)\*\*/g, '$1');
    listBuffer.push(text);
    return;
  }

  // Flush list if we hit a non-list line
  if (inList && line.trim() !== '') {
    flushList();
  }

  // Empty line
  if (line.trim() === '') {
    flushList();
    doc.moveDown(0.4);
    return;
  }

  // Regular paragraph
  const text = line
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/`(.*?)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');

  doc.fillColor(TEXT).font('Helvetica').fontSize(11).text(text, { width: W });
}

// Cover page
doc.fillColor(TEXT).fontSize(11).font('Helvetica');
doc.moveDown(4);
doc.fillColor(ACCENT).fontSize(36).font('Helvetica-Bold').text('How to Build an', { align: 'center' });
doc.fillColor(TEXT).fontSize(42).text('AI Corporation', { align: 'center' });
doc.moveDown(0.5);
doc.fillColor(MUTED).fontSize(16).font('Helvetica').text("The Founder's Playbook for AI-Native Businesses", { align: 'center' });
doc.moveDown(2);
doc.fillColor('#e0e0e0').rect(doc.page.margins.left + W/3, doc.y, W/3, 1).fill('#e0c060');
doc.moveDown(2);
doc.fillColor(ACCENT).fontSize(13).font('Helvetica-Bold').text('By Incagent DAO LLC', { align: 'center' });
doc.fillColor(MUTED).fontSize(11).font('Helvetica').text('Wyoming Decentralized Autonomous Organization', { align: 'center' });
doc.moveDown(0.4);
doc.fillColor(MUTED).fontSize(11).text('AI-Operated · Filed 2026', { align: 'center' });

// Content
doc.addPage();
doc.fillColor(TEXT).fontSize(11).font('Helvetica');

lines.forEach(line => renderLine(line));
flushList();
flushTable();

doc.end();
out.on('finish', () => console.log('PDF generated: guide/how-to-build-an-ai-corporation.pdf'));
out.on('error', e => console.error('Error:', e));
