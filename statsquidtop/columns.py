columns = [
        {
            'header': 'NAME',
            'width': 20,
            'value_func': lambda x: x['Names'][0].strip('/'),
            'is_bytes': False
        },
        {
            'header': 'CPU %',
            'width': 8,
            'value_func': lambda x: round(x['CPUPercentage'], 2),
            'is_bytes': False
        },
        {
            'header': 'MEM',
            'width': 10,
            'value_func': lambda x: x['memory_stats']['usage'],
            'is_bytes': True
        },
        {
            'header': 'NET TX',
            'width': 10,
            'value_func': lambda x: x['TxBytesTotal'],
            'is_bytes': True
        },
        {
            'header': 'NET RX',
            'width': 10,
            'value_func': lambda x: x['RxBytesTotal'],
            'is_bytes': True
        },
        {
            'header': 'IO READ',
            'width': 10,
            'value_func': lambda x: x['IoReadBytesTotal'],
            'is_bytes': True
        },
        {
            'header': 'IO WRITE',
            'width': 10,
            'value_func': lambda x: x['IoWriteBytesTotal'],
            'is_bytes': True
        },
        {
            'header': 'NODE',
            'width': 11,
            'value_func': lambda x: x['NodeName'],
            'is_bytes': False
        }
    ]

hidden_columns = [
        {
            'header': 'ID',
            'value_func': lambda x: x['ID'][:12],
            'is_bytes': False
        },
        {
            'header': 'IMAGE',
            'value_func': lambda x: x['Image'],
            'is_bytes': False
        }
    ]
