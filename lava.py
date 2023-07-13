import pandas as pd
import numpy as np
import streamlit as st
import datetime
from dateutil.relativedelta import relativedelta
import _financial as npf
import pytz
from pandas.tseries.offsets import MonthEnd
# from st_snowauth import snowauth_session
# https://github.com/sfc-gh-bhess/st_snowauth/tree/main

# st.markdown("## This (and above) is always seen")
# session = snowauth_session()
# st.markdown("## This (and below) is only seen after authentication")

# make changes here

st.title("LAVA App")

col_11, col_12 = st.columns(2)
with col_11:
    st.write('Test or actual?')
with col_12:
    # Dropdown menu for test or actual
    st.selectbox(
        label = 'Test or actual', 
        options = ('Test', 'Actual'), 
        label_visibility='collapsed'
    )

col_21, col_22 = st.columns(2)
with col_21:
    st.write('Current time EST:')
with col_22:
    # current time in EST
    current_time = datetime.datetime.now(pytz.timezone('US/Eastern'))
    current_time_str = current_time.strftime("%m/%d/%Y %H:%M:%S")
    st.write(current_time_str)

col_31, col_32 = st.columns(2)
with col_31:
    st.write('Analyst:')
with col_32:
    # analyst name
    analyst_name = 'To be implemented'
    st.write(analyst_name)

col_41, col_42 = st.columns(2)
with col_41:
    st.write('Analyst email:')
with col_42:
    # analyst email
    st.selectbox(
        label = 'Analyst email',
        options = ('wenzheng.li@hl.com', 'xuezhu.yang@hl.com'),
        label_visibility='collapsed'
    )

col_51, col_52 = st.columns(2)
with col_51:
    st.write('Officer email:')
with col_52:
    # officer email
    st.selectbox(
        label = 'Officer email',
        options = ('sai.uppuluri@hl.com', 'amacnamara@hl.com'),
        label_visibility='collapsed'
    )


# Upload file
uploaded_file = st.file_uploader(
    label = "Upload File", 
    type = ["csv", "xlsx"], 
    key = "file_uploader",
    help = "Upload a file with Tape, InputVectors and InputInterestRates"
)

if uploaded_file is not None:
    data_state_text = st.empty()
    data_state_text.text('Reading data...')
    if uploaded_file.name.endswith("xlsx"):
        # Sheet names are fixed for now
        df_tape = pd.read_excel(uploaded_file, sheet_name = 'Tape')
        df_vectors = pd.read_excel(uploaded_file, sheet_name = 'InputVectors')
        df_vectors = df_vectors.set_index('Period')
        df_interest_rates = pd.read_excel(uploaded_file, sheet_name = 'InputInterestRates')
        df_interest_rates = df_interest_rates.set_index('Period')
    else:
        raise Exception("Uploaded file not in xlsx format")
    data_state_text.text('Reading data...done!')

    # Temperarily focus on Monthly payment frequency only
    df_tape = df_tape[df_tape['Payment Frequncy'] == 'Monthly']

    st.text('Tape: ')
    st.write(df_tape)

    # Model Begins --------------------------------------------------------------------------------------------------------
    dict_all = {
        'loan_id':[],
        'period_num':[],
        'period':[],
        'principal_balance':[],
        'scheduled_principal':[],
        'prepayment':[],
        'default':[],
        'interest':[],
        'principal_cashflow':[]
    }

    # iterate through each loan
    progress_state = st.empty()
    for row_idx in range(len(df_tape)):
        progress_state.text('Processing loan: ' + str(row_idx + 1) +  ' / ' + str(len(df_tape)))
        dict_loan = {
            'loan_id':[],
            'period_num':[],
            'period':[],
            'principal_balance':[],
            'scheduled_principal':[],
            'prepayment':[],
            'default':[],
            'interest':[],
            'principal_cashflow':[]
        }

        row = df_tape.iloc[row_idx, :]
        start_period = row['Period#']
        end_period = row['Total Periods']
        start_date_str = row['Next Payment Date']
        payment_frequency = row['Payment Frequncy']
        benchmark = row['Benchmark']

        # convert Next Payment Date to datetime
        if type(start_date_str) == str:
            date_format_list = ['%m/%d/%y', '%m/%d/%Y']
            for i in range(len(date_format_list)):
                date_format = date_format_list[i]
                try:
                    start_date = datetime.datetime.strptime(start_date_str, date_format)
                    break
                except:
                    if i == len(date_format_list) - 1:
                        raise Exception("Unhandled date format in Next Payment Date")
        else:
            start_date = start_date_str.to_pydatetime()

        # iterate through each period
        for current_period in range(start_period, end_period + 1):
            i = current_period - start_period
            # https://stackoverflow.com/questions/4130922/how-to-increment-datetime-by-custom-months-in-python-without-using-library
            if payment_frequency == 'Monthly':
                current_date = start_date + relativedelta(months=i)
            elif payment_frequency == 'Weekly':
                current_date = start_date + relativedelta(weeks=int(i))
            else:
                raise Exception("Unhandled payment frequency")

            # calculate principal balance
            if i == 0:
                principal_balance = row['Outstanding Principal Balance']
            else:
                principal_balance = dict_loan['principal_balance'][i-1] - dict_loan['default'][i-1] - dict_loan['principal_cashflow'][i-1]

            scheduled_principal = -npf.ppmt(row['Interest rate margin'] / 12, 1, end_period - current_period + 1, principal_balance)

            # calculate interest
            if pd.isnull(benchmark):
                interest_rate = row['Interest rate margin']
            else:
                interest_rate = row['Interest rate margin'] + df_interest_rates.loc[current_period, benchmark]
                
            interest = min(
                principal_balance - scheduled_principal,
                principal_balance * interest_rate / 12
            )

            # calculate default
            default = min(
                principal_balance - scheduled_principal - interest,
                principal_balance * df_vectors.loc[current_period, 'Default']
            )
            
            # calculate prepayment
            prepayment = min(
                principal_balance - scheduled_principal - interest - default,
                principal_balance * df_vectors.loc[current_period, 'Prepay']
            )

            # calculate principal cashflow
            principal_cashflow = scheduled_principal + prepayment

            # Update loan level dictionary - add one period
            dict_loan['loan_id'].append(row['Loan #'])
            dict_loan['period_num'].append(current_period)
            dict_loan['period'].append(current_date)
            dict_loan['principal_balance'].append(principal_balance)
            dict_loan['scheduled_principal'].append(scheduled_principal)
            dict_loan['prepayment'].append(prepayment)
            dict_loan['default'].append(default)
            dict_loan['interest'].append(interest)
            dict_loan['principal_cashflow'].append(principal_cashflow)

        # Update dictionary for all loans
        dict_all['loan_id'].extend(dict_loan['loan_id'])
        dict_all['period_num'].extend(dict_loan['period_num'])
        dict_all['period'].extend(dict_loan['period'])
        dict_all['principal_balance'].extend(dict_loan['principal_balance'])
        dict_all['scheduled_principal'].extend(dict_loan['scheduled_principal'])
        dict_all['prepayment'].extend(dict_loan['prepayment'])
        dict_all['default'].extend(dict_loan['default'])
        dict_all['interest'].extend(dict_loan['interest'])
        dict_all['principal_cashflow'].extend(dict_loan['principal_cashflow'])

    # Model Ends --------------------------------------------------------------------------------------------------------


    # Create Outputs --------------------------------------------------------------------------------------------------------
    # Loan level output
    df_loan_output = pd.DataFrame(dict_all)
    st.text('Loan level output: ')
    st.dataframe(df_loan_output)

    # https://discuss.streamlit.io/t/download-button-for-csv-or-xlsx-file/17385/2
    download_button_loan = st.download_button(
        label = 'Download loan level output', 
        data = df_loan_output.to_csv(index=False), 
        file_name = 'LoanLevelOutput.csv', 
        mime = 'text/csv',
        key = 'download_button_loan'
    )

    # Calculate end of month from period
    # https://stackoverflow.com/questions/37354105/find-the-end-of-the-month-of-a-pandas-dataframe-series
    df_loan_output['MonthEnd'] = pd.to_datetime(df_loan_output['period'], format="%Y%m") + MonthEnd(0)

    # Group by Monthend, and calculate aggregate sum of principal balance, scheduled principal, prepayment, default, interest, principal cashflow
    df_portfolio_output = df_loan_output[[
        'MonthEnd', 
        'principal_balance', 
        'scheduled_principal',
        'prepayment',
        'default',
        'interest',
        'principal_cashflow'
    ]].groupby('MonthEnd').sum().reset_index()
    
    # Portfolio level output
    st.text('Portfolio level output: ')
    st.dataframe(df_portfolio_output)

    download_button_portfolio = st.download_button(
        label = 'Download portfolio level output', 
        data = df_portfolio_output.to_csv(index=False), 
        file_name = 'PortfolioLevelOutput.csv', 
        mime = 'text/csv',
        key = 'download_button_portfolio'
    )
    


