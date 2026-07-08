# Worker to transform dataset and get climate data.

This project can transform dataset according differences way.

1. You can extra some features according to rules with name of features.

2. Keep only features that have some characteristic like percentage of missing values.

3. Search climatic data with geo localization and start and end dates.

4. Normalize data


## Search climatic data

This service work with [power service](https://power.larc.nasa.gov/api/temporal/hourly/point) to get data from temperature, precipitation, uv and other.

You can see all variable on [clime](/tasks/src/search_data/clima.json)


## Develop

The docker Image can build with docker compose to run and attach to this container to continue develop on it.

1. Build the images
```shell
docker compose -f compose.dev.yaml build
```

2. Run the contained
```shell
docker compose -f compose.dev.yaml up -d
```
3. Access to docker
```shell
docker compose -f compose.dev.yaml exec -it tasksdd bash
```

4. To run the celery task

```shell
watchmedo auto-restart --directory=./ --pattern=*.py --recursive -- celery -A tasks worker --loglevel=INFO
```

Some examples of command to run on dev mode:

* Missing values
```shell
python tasks_test.py missing_fill_average correlation_Dataset_clean.csv
```

* Normalize file

```shell
python tasks_test.py normalize_dataset lrace_trueba_fill_clean.csv zero_to_one Rendimiento
```
* Search weather data with selected variables
``` shell
python tasks_test.py search_data_power_hourly 3.14_lrace_geo.csv all '{"latitude_column": "Lat", "longitude_column": "Long", "start_date_column": "DateStart", "end_date_column": "DateEnd"  }' 'ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_KT,ALLSKY_SFC_LW_DWN,ALLSKY_SFC_PAR_TOT,CLRSKY_SFC_PAR_TOT,ALLSKY_SFC_UVA,ALLSKY_SFC_UVB,ALLSKY_SFC_UV_INDEX,T2M,T2MDEW,T2MWET,TS,T2M_RANGE,T2M_MAX,T2M_MIN,QV2M,RH2M,PRECTOTCORR,PS,WS10M,WS10M_MAX,WS10M_MIN,WS10M_RANGE,WD10M,WS50M,WS50M_MAX,WS50M_MIN,WS50M_RANGE,WD50M'
```
* Search weather with all variables
```shell
python tasks_test.py search_data_power_hourly 3.14_lrace_geo.csv all '{"latitude_column": "Lat", "longitude_column": "Long", "start_date_column": "DateStart", "end_date_column": "DateEnd"  }' 'ALL_ALL'
```

* Search weather with all variables by month
```shell
python tasks_test.py search_data_power_monthly 2.LRACE_FGeolocalizacion.csv all '{"latitude_column": "lat", "longitude_column": "lon", "start_date_column": "DateStart", "end_date_column": "DateEnd"  }' 'ALL_ALL'
```

## About author


In collaboration with the [Universidad Autonoma del Estado de Mexico](https://www.uaemex.mx/)  and supported by [CONAHCYT](https://conahcyt.mx/) scholarships, this project was created. For new features, changes, or improvements, please reach out to:

Student, Ph.D. Juan Carlos Moreno Sanchez
<carlos.moreno.phd@gmail.com>
<jcmorenos001@alumno.uaemex.mx>



