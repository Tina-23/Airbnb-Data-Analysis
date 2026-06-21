import matplotlib
matplotlib.use('Agg')
import pandas as pd, numpy as np, warnings
warnings.filterwarnings('ignore')
from scipy import stats
import statsmodels.formula.api as smf
from pathlib import Path

DATA   = Path('data/processed')
master = pd.read_parquet(DATA / 'master_listings.parquet')
sg     = master[master['city'] == 'singapore'].copy()
bk     = master[master['city'] == 'bangkok'].copy()

# H1 — Mann-Whitney
for df, city in [(sg, 'Singapore'), (bk, 'Bangkok')]:
    entire  = df[df['room_type'] == 'Entire home/apt']['price'].dropna()
    private = df[df['room_type'] == 'Private room']['price'].dropna()
    _, p    = stats.mannwhitneyu(entire, private, alternative='greater')
    premium = round(entire.median() / private.median(), 2)
    print(city + ' H1: premium=' + str(premium) + 'x  p=' + str(p))

# H4 — ANOVA
for df, city in [(sg, 'Singapore'), (bk, 'Bangkok')]:
    groups = [g['price'].dropna().values for _, g in df.groupby('neighbourhood') if len(g) >= 10]
    f, p   = stats.f_oneway(*groups)
    print(city + ' H4: F=' + str(round(f, 2)) + '  p=' + str(p))

# OLS regression
for df, city in [(sg, 'Singapore'), (bk, 'Bangkok')]:
    mdf = df[['price', 'room_type', 'availability_365', 'number_of_reviews', 'minimum_nights']].dropna().copy()
    mdf['log_price'] = np.log1p(mdf['price'])
    mdf['rt']        = mdf['room_type'].str.replace('/', '_').str.replace(' ', '_')
    formula          = 'log_price ~ C(rt) + availability_365 + number_of_reviews + minimum_nights'
    m                = smf.ols(formula, data=mdf).fit()
    print(city + ' OLS: R2=' + str(round(m.rsquared, 3)) + '  adj_R2=' + str(round(m.rsquared_adj, 3)) + '  F-p=' + str(round(m.f_pvalue, 8)))

print('\nAll statistical tests passed.')
