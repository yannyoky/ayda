# Reference data

`cities.csv`: Russian cities with population, coordinates and time zone, derived from
[hflabs/city](https://github.com/hflabs/city) (© HFLabs, CC BY-SA 4.0). This derived file is
distributed under the same license. Changes: kept id, name, region, IANA time zone (mapped from
the UTC offset and region), coordinates rounded to 4 digits and population. Ids are stable: new
cities are appended, existing ids are never reused.
