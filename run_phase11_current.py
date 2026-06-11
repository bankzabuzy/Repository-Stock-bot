from phase11_global_hedgefund_os.data_feed.multi_source import MultiSourceFeed

def main():
    feed = MultiSourceFeed()
    data = feed.fetch(["AAPL","NVDA","GLD"])
    print(data)

if __name__ == "__main__":
    main()
