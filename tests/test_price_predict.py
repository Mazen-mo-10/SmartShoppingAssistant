from models.price_classifier import price_classifier
print('price_classifier object:', price_classifier)
if price_classifier is None:
    print('price_classifier is None')
else:
    print('loaded flag:', price_classifier.loaded)
    try:
        res = price_classifier.predict('Samsung Galaxy S24 Ultra', 'A flagship phone', 35000)
        print('predict result ->', res)
    except Exception as e:
        print('prediction raised', e)
