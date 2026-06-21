import pandas as pd
import numpy as np
import statsmodels.formula.api as smf
import warnings
warnings.filterwarnings('ignore')

master = pd.read_parquet('data/processed/master_listings.parquet')

for city, use_nb in [('singapore', True), ('bangkok', False)]:
    df = master[master['city'] == city].copy()
    cols = ['price', 'room_type', 'neighbourhood', 'availability_365',
            'number_of_reviews', 'minimum_nights', 'reviews_per_month',
            'calculated_host_listings_count', 'nb_median_price']
    m = df[[c for c in cols if c in df.columns]].dropna().copy()
    m['log_price'] = np.log1p(m['price'])
    m['log_nb_median_price'] = np.log1p(m['nb_median_price'])
    m['room_type'] = m['room_type'].str.replace('/', '_').str.replace(' ', '_')

    base_f = 'log_price ~ C(room_type, Treatment("Private_room")) + availability_365 + number_of_reviews + minimum_nights'
    base = smf.ols(base_f, data=m).fit()

    if use_nb:
        enh_f = ('log_price ~ C(room_type, Treatment("Private_room")) + C(neighbourhood)'
                 ' + availability_365 + number_of_reviews + minimum_nights'
                 ' + reviews_per_month + calculated_host_listings_count + log_nb_median_price')
    else:
        enh_f = ('log_price ~ C(room_type, Treatment("Private_room"))'
                 ' + availability_365 + number_of_reviews + minimum_nights'
                 ' + reviews_per_month + calculated_host_listings_count + log_nb_median_price')

    enh = smf.ols(enh_f, data=m).fit()
    print(f'{city.capitalize()}: baseline R2={base.rsquared:.3f}  enhanced R2={enh.rsquared:.3f}  adj_R2={enh.rsquared_adj:.3f}  obs={int(enh.nobs):,}')
