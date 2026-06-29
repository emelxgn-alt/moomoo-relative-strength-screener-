# Moomoo Relative Strength Screener
Think of this like a stock race.
The script asks:
- Did this stock run faster than its market index?
- Did this stock run faster than its sector?
- Did it do that over 1 month, 3 months, and 6 months?
Then it gives every stock a score and puts the strongest ones at the top.
## Before You Run It
1. Open moomoo OpenD.
2. Make sure OpenD is logged in and running.
3. Install the two Python packages:
```powershell
pip install futu-api pandas
```
## Run A Tiny Test First
```powershell
python outputs\moomoo_relative_strength_screener.py --limit-per-market 5 --top 20
```
## Run The Full Screener
```powershell
python outputs\moomoo_relative_strength_screener.py
```
## What You Get
It prints the top stocks on screen and saves:
```text
relative_strength_screener.csv
```
## Important
The default index codes are:
- Singapore: SG.STI
- Hong Kong: HK.HSI
- United States: US.SPX
If moomoo uses a different code in your account, you can change it like this:
```powershell
python outputs\moomoo_relative_strength_screener.py --index-code US=US.SPX
```
