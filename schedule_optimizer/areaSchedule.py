import pandas as pd
import datetime

# {<date>: [231,321,424, 323.... 123]} Alltså 96 index med ett kw för varje kvart. 


class schedule:
    def __init__ (self):
        self.timeLineDay: list = []
        self.timeLineTotal: dict = {}

    def getDay(self, date : datetime):
        # Dont know what format the date will be yet 
        return self.timeLineTotal[pd.to_datetime(date)]

    



