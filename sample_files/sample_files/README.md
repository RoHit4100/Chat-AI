# Sample files for testing and the demo video

All data is fictional. Use these to test every supported file type, plus failure cases.

## Demo files (the three used in the video)
| File | What it is | Answers to check |
|---|---|---|
| project_report.pdf | 2-page status report for "Project Orion" | Led by Meera Iyer; launch 14 Mar 2026; budget INR 48 lakh, spent INR 31.5 lakh (65.6%); status amber because data migration is 2 weeks late; 3 risks listed on page 2 |
| sales.xlsx | 12 months of 2025 sales (Month, Revenue (INR), Units Sold, Top Region) | Top 3 by revenue: Nov 1,925,000; Oct 1,840,000; Aug 1,785,000. Lowest: Feb 1,085,000. Total revenue: 18,585,000. Total units: 6,136 |
| traffic_chart.png | Bar chart, website visits by channel, Sept 2025 | Organic search 42,000; Direct 28,500; Referral 15,200; Social media 9,800; Email 6,400 |

## Other supported types
| File | Type | Answers to check |
|---|---|---|
| feedback_summary.docx | DOCX | Satisfaction 4.2/5 (up from 3.9); 120 customers; top request: faster report loading (37) |
| product_pitch.pptx | PPTX, 3 slides | Problem: data in 5 spreadsheets, reports take 3 days; ask: INR 48 lakh |
| customers.csv | CSV, 10 rows | 3 Enterprise customers at 12,000 each; cities include Mumbai, Pune, Thane |
| config.json | JSON | version 1.4.2; max_upload_mb 25; rate limit 60 per minute |
| notes.txt | Plain text | Four regions; action item for Meera: book training rooms for Feb 2026 |
| hello.py | Code | moving_average function; raises ValueError if window <= 0 |
| docs_bundle.zip | ZIP with notes.txt, config.json, hello.py | Each member should be read as a normal file |

## Failure cases (should fail gracefully with a clear message)
| File | Expected result |
|---|---|
| corrupt.pdf | Truncated PDF: "could not read this PDF" style error, no crash |
| installer.exe | Plain text named .exe: rejected as an unsupported type |
| oversized file | Create one on demand (below), upload, expect a size-limit error |

Create a 30 MB file and a path-traversal ZIP for extra tests:
```bash
head -c 30000000 /dev/urandom > oversized.bin
python3 -c "import zipfile; z=zipfile.ZipFile('traversal.zip','w'); z.writestr('../evil.txt','x'); z.close()"
```
Expected: oversized.bin is rejected for size (and type); traversal.zip is rejected or the unsafe member is skipped.
